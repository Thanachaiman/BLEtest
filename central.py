# This example finds and connects to a peripheral running the
# UART service (e.g. ble_simple_peripheral.py).

import bluetooth
import random
import struct
import time
import micropython
from machine import Pin

from ble_advertising import decode_services, decode_name

from micropython import const



_ADV_IND = const(0x00)
_ADV_DIRECT_IND = const(0x01)
_ADV_SCAN_IND = const(0x02)
_ADV_NONCONN_IND = const(0x03)

Sensor_UUID = bluetooth.UUID(0x181A)
_temp = bluetooth.UUID(0x2A6E) 
_humi = bluetooth.UUID(0x2A6F)


COUNT_UUID = bluetooth.UUID(0x181C)
_NUM =     bluetooth.UUID(0x2B90)
_switch = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E")



class BLESimpleCentral:
    def __init__(self, ble):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        self._reset()
        
    
    def _reset(self):
        # Cached name and address from a successful scan.
        self._name = None
        self._addr_type = None
        self._addr = None

        # Callbacks for completion of various operations.
        # These reset back to None after being invoked.
        self._scan_callback = None
        self._conn_callback = None
        self._read_callback = None

        # Persistent callback for when new data is notified from the device.
        self._notify_callback = None

        # Connected device.
        self._conn_handle = None
        self._start_handle = None
        self._end_handle = None
        self._temp = None
        self._switch = None
        self._humi = None
        self._num = None
    
        
    def _irq(self, event, data):
        if event == 5: # _IRQ_SCAN_RESULT
            addr_type, addr, adv_type, rssi, adv_data = data
            if adv_type in (_ADV_IND, _ADV_DIRECT_IND) and Sensor_UUID in decode_services(
                adv_data
            ):
                # Found a potential device, remember it and stop scanning.
                self._addr_type = addr_type
                self._addr = bytes(
                    addr
                )  # Note: addr buffer is owned by caller so need to copy it.
                self._name = decode_name(adv_data) or "?"
                self._ble.gap_scan(None)

        elif event == 6: # _IRQ_SCAN_DONE
            if self._scan_callback:
                if self._addr:
                    # Found a device during the scan (and the scan was explicitly stopped).
                    self._scan_callback(self._addr_type, self._addr, self._name)
                    self._scan_callback = None
                else:
                    # Scan timed out.
                    self._scan_callback(None, None, None)

        elif event == 7: #_IRQ_PERIPHERAL_CONNECT
            # Connect successful.
            conn_handle, addr_type, addr = data
            if addr_type == self._addr_type and addr == self._addr:
                self._conn_handle = conn_handle
                self._ble.gattc_discover_services(self._conn_handle)

        elif event == 8: #_IRQ_PERIPHERAL_DISCONNECT
            # Disconnect (either initiated by us or the remote end).
            conn_handle, _, _ = data
            if conn_handle == self._conn_handle:
                # If it was initiated by us, it'll already be reset.
                self._reset()
                
        elif event == 9: # _IRQ_GATTC_SERVICE_RESULT
            # Connected device returned a service.
            conn_handle, start_handle, end_handle, uuid = data
            print("service", data)
            if conn_handle == self._conn_handle and uuid == Sensor_UUID:
                self._start_handle, self._end_handle = start_handle, end_handle
            if conn_handle == self._conn_handle and uuid == COUNT_UUID:
                self._start_handle2, self._end_handle2 = start_handle, end_handle
             
        elif event == 10: # _IRQ_GATTC_SERVICE_DONE
            self._ble.gattc_discover_characteristics(self._conn_handle, self._start_handle, self._end_handle)
            time.sleep_ms(1000)
            self._ble.gattc_discover_characteristics(self._conn_handle, self._start_handle2, self._end_handle2)


            
        
        elif event == 11: # _IRQ_GATTC_CHARACTERISTIC_RESULT
            # Connected device returned a characteristic.
            conn_handle, def_handle, value_handle, properties, uuid = data
            print(uuid)

            if conn_handle == self._conn_handle and uuid == _switch:
                print("rx service.")
                self._switch = value_handle
            if conn_handle == self._conn_handle and uuid == _temp:
                self._temp = value_handle
                print("tx service.")
            if conn_handle == self._conn_handle and uuid == _humi:
                self._humi = value_handle
                print("tx2 service.")
            if conn_handle == self._conn_handle and uuid == _NUM:
                print("text service.")
                self._num = value_handle

            
                
        elif event == 12: # _IRQ_GATTC_CHARACTERISTIC_DONE
            print("event == _IRQ_GATTC_CHARACTERISTIC_DONE")
#             # Characteristic query complete.
            if self._temp is not None and self._switch is not None and self._humi is not None:
                # We've finished connecting and discovering device, fire the connect callback.
                if self._conn_callback:
                    self._conn_callback()
            else:
                print("Failed to find uart rx characteristic.")


        elif event == 17: # _IRQ_GATTC_WRITE_DONE
            conn_handle, value_handle, status = data
            print("TX complete")

        elif event == 18: # _IRQ_GATTC_NOTIFY:
            conn_handle, value_handle, notify_data = data
            if conn_handle == self._conn_handle and value_handle == self._humi:
                if self._notify_callback:
                    self._notify_callback(notify_data)
            if conn_handle == self._conn_handle and value_handle == self._temp:
                if self._notify_callback:
                    self._notify_callback(notify_data)
            if conn_handle == self._conn_handle and value_handle == self._num:
                if self._notify_callback:
                    self._notify_callback(notify_data)
                
                
    def is_connected(self):
        return (
            self._conn_handle is not None
            and self._temp is not None
            and self._switch is not None
            and self._humi is not None
            and self._num is not None
        )

    # Find a device advertising the environmental sensor service.
    def scan(self, callback=None):
        self._addr_type = None
        self._addr = None
        self._scan_callback = callback
        self._ble.gap_scan(2000, 30000, 30000)

    # Connect to the specified device (otherwise use cached address from a scan).
    def connect(self, addr_type=None, addr=None, callback=None):
        self._addr_type = addr_type or self._addr_type
        self._addr = addr or self._addr
        self._conn_callback = callback
        if self._addr_type is None or self._addr is None:
            return False
        self._ble.gap_connect(self._addr_type, self._addr)
        return True

    # Disconnect from current device.
    def disconnect(self):
        if not self._conn_handle:
            return
        self._ble.gap_disconnect(self._conn_handle)
        self._reset()
    
    def write(self, v, response=False):
        if not self.is_connected():
            return
        self._ble.gattc_write(self._conn_handle, self._switch, v, 1 if response else 0)

    # Set handler for when data is received over the UART.
    def on_notify(self, callback):
        self._notify_callback = callback



def demo():
    ble = bluetooth.BLE()
    central = BLESimpleCentral(ble)

    not_found = False

    def on_scan(addr_type, addr, name):
        if addr_type is not None:
            print("Found peripheral:", addr_type, addr, name)
            central.connect()
        else:
            nonlocal not_found
            not_found = True
            print("No peripheral found.")

    central.scan(callback=on_scan)

    # Wait for connection...
    while not central.is_connected():
        time.sleep_ms(100)
        if not_found:
            return

    print("Connected")

    def no_input(v):
        print(bytes(v[:]))

    central.on_notify(no_input)

    with_response = False

    i = 0
    but = Pin(27, Pin.IN)
    while central.is_connected():
        try:
            central.write(str(but.value()), with_response)
        except:
            print("switch failed")
        i += 1
        time.sleep_ms(1000 if with_response else 500)

    print("Disconnected")


if __name__ == "__main__":
    demo()
