#!/usr/bin/python
# -*- coding: UTF-8 -*-
# file name：server.py

import socket  # import socket module

s = socket.socket()  # create socket object
host = socket.gethostname()  # gain the local host name
port = 12345  # set the port
s.bind((host, port))  # bind the host and port

s.listen(5)  # wait for client connection
print('Waiting for connection...')
while True:
    c, addr = s.accept()  # accept the client connection
    print("Connection Address:", addr)
    c.send("Welcome to the socket server!".encode('utf-8'))
    c.close()  # close the connection
    break
s.close() # close the server socket