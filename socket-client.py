#!/usr/bin/python
# -*- coding: UTF-8 -*-
# file name：client.py

import socket  # import socket module

s = socket.socket()  # create socket object
host = socket.gethostname()  # gain the local host name (server)
port = 12345  # set the port (server)

s.connect((host, port)) # request the connection to the server
print(s.recv(1024)) # print the received message from the server, 1024 denotes the size of message buffers
s.close() # close the connection to the server