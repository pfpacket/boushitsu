#!/usr/bin/env python3

import RPi.GPIO as GPIO
from time import sleep

light_out = 14
light_in = 15


def isOpen():
    GPIO.cleanup()
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(light_out, GPIO.OUT)
    GPIO.setup(light_in, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.output(light_out, GPIO.HIGH)
    # if GPIO.input(light_in) == GPIO.HIGH:
    #       print("True")
    # elif GPIO.input(light_in) == GPIO.LOW:
    #       print("False")
    result = (GPIO.input(light_in) == GPIO.HIGH)
    GPIO.cleanup()
    return result


if __name__ == "__main__":
    while True:
        print(isOpen())
        sleep(0.5)
