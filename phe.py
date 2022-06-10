import bluetooth
import random
import struct
import time
from ble_advertising import advertising_payload
import dht
import ubluetooth
from machine import Pin
from micropython import const


# define UUID bluetooth 
Sensor_UUID = bluetooth.UUID(0x181A)
COUNT_UUID = bluetooth.UUID(0x181C)


# define UUID and FLAG off Characteristic
_temp = (
    bluetooth.UUID(0x2A6E),
    ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,
)
_switch = (
    bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
    ubluetooth.FLAG_WRITE | ubluetooth.FLAG_WRITE_NO_RESPONSE,
)
_humidity = (
    bluetooth.UUID(0x2A6F),
    ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,
)

_NUM = (
    bluetooth.UUID(0x2B90),
    ubluetooth.FLAG_READ | ubluetooth.FLAG_NOTIFY,
)


# define SERVICE
_SENSOR_SERVICE = (
    Sensor_UUID,                      # define UUID of SERVICE
    (_temp, _humidity),               # define UUID of Characteristic 2 
)

_COUNT_SERVICE = (
    COUNT_UUID,
    (_NUM, _switch,)
)



class BLESimplePeripheral:
    def __init__(self, ble, name="BLE-TEST"):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._handle_temp, self._handle_temp2),(self._handle_num, self._handle_switch), # สร้างตัวแปรให้แต่ละ Characteristic
         ) = self._ble.gatts_register_services((_SENSOR_SERVICE, _COUNT_SERVICE)) # ลงทะเบียน SERVICE
        self._connections = set()
        self._write_callback = None
        self._payload = advertising_payload(name=name, services=[Sensor_UUID]) #advertise เป็นชื่อ name 
        self._advertise()

    def _irq(self, event, data):

        if event == 1: #_IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            print("New connection", conn_handle)
            self._connections.add(conn_handle)
        elif event == 2: #_IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            print("Disconnected", conn_handle)
            self._connections.remove(conn_handle)
            # Start advertising again to allow a new connection.
            self._advertise()
        elif event == 3: #_IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            value = self._ble.gatts_read(value_handle)
            if value_handle == self._handle_switch and self._write_callback:
                self._write_callback(value)

    def send(self, data, des):
        for conn_handle in self._connections:
            if des == 1:
                self._ble.gatts_notify(conn_handle, self._handle_temp, data)
            elif des == 2:
                self._ble.gatts_notify(conn_handle, self._handle_temp2, data)
            elif des == 3:
                self._ble.gatts_notify(conn_handle, self._handle_num, data)
            

    def is_connected(self):
        return len(self._connections) > 0

    def _advertise(self, interval_us=500000):
        print("Starting advertising")
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

    def on_write(self, callback):
        self._write_callback = callback


def demo():
    led = Pin(2, Pin.OUT)
    ble = bluetooth.BLE()
    p = BLESimplePeripheral(ble)

    def input(v):
        a = str(v)
        print("input =", a)
        if v == 0:
            led.value(0)
        else :
            led.value(1)
            
            

    p.on_write(input)
    a = 0
    while True:
        if p.is_connected():
            # Short burst of queued notifications.
            sensor = dht.DHT22(Pin(25))
            sensor.measure()
            temp = sensor.temperature()
            humi = sensor.humidity()
            print("temperature: %3.1f" %temp)
            print("Huminity: %3.1f" %humi)
            tempstr = str(temp)
            humistr = str(humi)
            p.send(tempstr, 1)
            p.send(humistr, 2)
            data = str(a) 
            p.send(data, 3)
            a += 1
        time.sleep_ms(1000)


if __name__ == "__main__":
    demo()


