#!/usr/bin/env python3

import cv2
import depthai as dai
import numpy as np
import argparse
import time
import blobconverter
from infer import gdnet

NN_WIDTH, NN_HEIGHT = 256, 256
# NN_PATH = blobconverter.from_openvino(
#     "MiDaS_small.xml", "MiDaS_small.bin", shaves=6)
# --------------- Pipeline ---------------
# Start defining a pipeline
pipeline = dai.Pipeline()
pipeline.setOpenVINOVersion(version=dai.OpenVINO.VERSION_2021_4)

# Define a neural network
detection_nn = pipeline.create(dai.node.NeuralNetwork)
# detection_nn.setBlobPath(str(NN_PATH))
detection_nn.setBlobPath("../Models/blob/MiDaS_small.blob")

detection_nn.setNumPoolFrames(4)
detection_nn.input.setBlocking(False)
detection_nn.setNumInferenceThreads(2)

# Define camera
cam = pipeline.create(dai.node.ColorCamera)
cam.setPreviewSize(NN_WIDTH, NN_HEIGHT)
cam.setInterleaved(False)
cam.setFps(40)
cam.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)

# Create outputs
xout_cam = pipeline.create(dai.node.XLinkOut)
xout_cam.setStreamName("cam")

xout_nn = pipeline.create(dai.node.XLinkOut)
xout_nn.setStreamName("nn")

# Link
cam.preview.link(detection_nn.input)
detection_nn.passthrough.link(xout_cam.input)
detection_nn.out.link(xout_nn.input)

# --------------- Inference ---------------
# Pipeline defined, now the device is assigned and pipeline is started
with dai.Device(pipeline) as device:

    # Output queues will be used to get the rgb frames and nn data from the outputs defined above
    q_cam = device.getOutputQueue("cam", 4, blocking=False)
    q_nn = device.getOutputQueue(name="nn", maxSize=4, blocking=False)

    start_time = time.time()
    counter = 0
    fps = 0
    layer_info_printed = False
    while True:
        in_frame = q_cam.get()
        in_nn = q_nn.get()
        # print(type(in_frame))
        frame1 = in_frame.getCvFrame()
        # cv2.imshow("frame1",frame1)
        frame = gdnet(frame1)
        inv_frame = cv2.bitwise_not(frame)

        # mirror(frame1)

        # Get output layer
        pred = np.array(in_nn.getFirstLayerFp16()).reshape(
            (NN_HEIGHT, NN_WIDTH))

        # Scale depth to get relative depth
        d_min = np.min(pred)
        d_max = np.max(pred)
        depth_relative = (pred - d_min) / (d_max - d_min)

        # Color it
        depth_relative = np.array(depth_relative) * 255
        depth_relative = depth_relative.astype(np.uint8)
        depth_relative = cv2.applyColorMap(
            depth_relative, cv2.COLORMAP_INFERNO)

        # Downscale frame
        frame = cv2.resize(frame, (NN_WIDTH//2, NN_HEIGHT//2))

        # Threshold Mask values
        ret, thresh1 = cv2.threshold(inv_frame, 120, 255, cv2.THRESH_BINARY)

        # Convert GrayScale to RGB for Bitwise AND compatibility (same number of channels)
        backtorgb = cv2.cvtColor(thresh1, cv2.COLOR_GRAY2RGB)

        # Apply Bitwise AND to MiDas output(depth_relative) and (Mask genereated by MirrorNet)
        final = cv2.bitwise_and(depth_relative, backtorgb)

        # cv2.imshow("frame", frame)
        # cv2.imshow("inv_frame", inv_frame)
        # cv2.imshow("backtorgb", backtorgb)
        # cv2.imshow("final", final)
        # cv2.imshow("test", depth_relative)
        Hori = np.concatenate((depth_relative, backtorgb, final), axis=1)
        cv2.imshow("Detections", Hori)

        counter += 1
        if (time.time() - start_time) > 1:
            fps = counter / (time.time() - start_time)

            counter = 0
            start_time = time.time()
            print(fps)

        if cv2.waitKey(1) == ord('q'):
            break