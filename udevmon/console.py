from pyudev import Context, Monitor
from loguru import logger
from multiprocessing import Process
from threading import Thread

import re
from pathlib import Path
import time
import sh

mon_devs = set(["1366:1051"])

USB_PAT =  re.compile(r"^/dev/bus/usb/(?P<bus>\d+)/(?P<device>\d+)$")

added_device = set() 

KVM_XML="""<hostdev mode="subsystem" type="usb" managed="yes">
  <source>
    <vendor id="0x{}"/>
    <product id="0x{}"/>
    <address bus="{}" device="{}"/>
  </source>
</hostdev>
"""

KVM_XML2="""<hostdev mode="subsystem" type="usb" managed="yes">
  <source>
    <address bus="{}" device="{}"/>
  </source>
</hostdev>
"""

def monitor_udev():
    ctx = Context()
    monitor = Monitor.from_netlink(ctx)
    filters = ["usb"]
    if filters:
        for filter in filters:
            monitor.filter_by(subsystem=filter)

    udev_events = set(["add", "remove"])

    for device in iter(monitor.poll, None):
        if device.action ==  "add":
            """
            Plugging a USB device may trigger multiple add actions here, eg a 4G modem would add multiple ttyUSB ports and a cdc-wdm port
            We'll launch callback_no_flood that will only execute callback once per CALLBACK_FLOOD_TIMEOUT
            """
            vendor_id = device.get("ID_VENDOR_ID")
            model_id = device.get("ID_MODEL_ID")
            if vendor_id and model_id:
                found_device = "{}:{}".format(vendor_id, model_id)
                logger.info(found_device)
                device_node = device.device_node
                if found_device in mon_devs:
                    m = USB_PAT.match(device_node)
                    if m:
                        added_device.add(device_node)
                        logger.info(
                            "Device {} {} as {} in bus {} device {}".format(found_device, device.action, device.device_node, m["bus"], m["device"])
                        )
                        add_device(vendor_id, model_id, int(m["bus"]), int(m["device"]))
            else:
                logger.debug("Added device: {}".format(device.device_node))

        if device.action == "remove":
            if device.device_node in added_device:
                m = USB_PAT.match(device.device_node)
                if m:
                    logger.info( "Device {} {} as {} in bus {} device {}".format(device, device.action, device.device_node, m["bus"], m["device"]))
                    remove_device(int(m["bus"]), int(m["device"]))
                added_device.remove(device.device_node)

def attach_kvm(xmlfile : Path):
    def sleep_and_attach(xmlfile : Path):
        time.sleep(2)
        logger.info(f"begin attach {xmlfile}")
        sh.virsh("attach-device","ubuntu22.04", xmlfile)

    p = Thread(target=sleep_and_attach, args=(xmlfile,))
    p.run()


def add_device(vendor_id : str, model_id : str, bus : int, device : int):
    tmp_file = Path( f"~/tmp/usb_{bus}_{device}.xml").expanduser()
    #tmp_file.write_text( KVM_XML.format( vendor_id, model_id, bus, device) )
    tmp_file.write_text( KVM_XML2.format( bus, device) )
    attach_kvm(tmp_file)

def detach_kvm(xmlfile : Path):
    def sleep_and_detach(xmlfile : Path):
        time.sleep(2)
        logger.info(f"begin attach {xmlfile}")
        sh.virsh("detach-device","ubuntu22.04", xmlfile)

    p = Thread(target=sleep_and_detach, args=(xmlfile,))
    p.run()


def remove_device(bus : int, device : int):
    tmp_file = Path( f"~/tmp/usb_{bus}_{device}.xml").expanduser()
    tmp_file.write_text( KVM_XML2.format(bus, device) )
    detach_kvm(tmp_file)



def main():
    monitor_udev()
