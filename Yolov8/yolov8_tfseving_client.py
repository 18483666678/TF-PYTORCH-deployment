import requests
import numpy as np
import cv2
import sys, os, shutil
import json
from PIL import Image, ImageDraw, ImageFont
import torch
import time
import torchvision
import math
import numpy
from PIL import JpegImagePlugin

class_names = ['lg']

rng = np.random.default_rng(3)
colors = rng.uniform(0, 255, size=(len(class_names), 3))

def nms(boxes, scores, iou_threshold):
    sorted_indices = np.argsort(scores)[::-1]

    keep_boxes = []
    while sorted_indices.size > 0:
        box_id = sorted_indices[0]
        keep_boxes.append(box_id)

        ious = compute_iou(boxes[box_id, :], boxes[sorted_indices[1:], :])
        keep_indices = np.where(ious < iou_threshold)[0]

        # print(keep_indices.shape, sorted_indices.shape)
        sorted_indices = sorted_indices[keep_indices + 1]

    return keep_boxes


def compute_iou(box, boxes):
    # xmin, ymin, xmax, ymax
    xmin = np.maximum(box[0], boxes[:, 0])
    ymin = np.maximum(box[1], boxes[:, 1])
    xmax = np.minimum(box[2], boxes[:, 2])
    ymax = np.minimum(box[3], boxes[:, 3])

    intersection_area = np.maximum(0, xmax - xmin) * np.maximum(0, ymax - ymin)

    box_area = (box[2] - box[0]) * (box[3] - box[1])
    boxes_area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union_area = box_area + boxes_area - intersection_area

    iou = intersection_area / union_area

    return iou

def xywh2xyxy(x):
    # Convert box (x, y, w, h) to box (x1, y1, x2, y2)
    y = np.copy(x)
    y[..., 0] = x[..., 0] - x[..., 2] / 2
    y[..., 1] = x[..., 1] - x[..., 3] / 2
    y[..., 2] = x[..., 0] + x[..., 2] / 2
    y[..., 3] = x[..., 1] + x[..., 3] / 2
    return y

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

def draw_detections(image, boxes, scores, class_ids, mask_maps=None, mask_alpha=0.3):
    img_height, img_width = image.shape[:2]
    size = min([img_height, img_width]) * 0.0006
    text_thickness = int(min([img_height, img_width]) * 0.001)

    mask_img = draw_masks(image, boxes, class_ids, mask_alpha, mask_maps)
    cv2.imshow("mask_maps", mask_img)
    cv2.waitKey(0)
    for box, score, class_id in zip(boxes, scores, class_ids):
        color = colors[class_id]

        x1, y1, x2, y2 = box.astype(int)
        cv2.rectangle(mask_img, (x1, y1), (x2, y2), color, 2)

        label = class_names[class_id]
        caption = f'{label} {int(score * 100)}%'
        (tw, th), _ = cv2.getTextSize(text=caption, fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                                      fontScale=size, thickness=text_thickness)
        th = int(th * 1.2)

        cv2.rectangle(mask_img, (x1, y1),
                      (x1 + tw, y1 - th), color, -1)

        cv2.putText(mask_img, caption, (x1, y1),
                    cv2.FONT_HERSHEY_SIMPLEX, size, (255, 255, 255), text_thickness, cv2.LINE_AA)

    return mask_img


def draw_masks(image, boxes, class_ids, mask_alpha=0.3, mask_maps=None):
    mask_img = image.copy()

    for i, (box, class_id) in enumerate(zip(boxes, class_ids)):
        color = colors[class_id]

        x1, y1, x2, y2 = box.astype(int)

        if mask_maps is None:
            cv2.rectangle(mask_img, (x1, y1), (x2, y2), color, -1)
        else:
            crop_mask = mask_maps[i][y1:y2, x1:x2, np.newaxis]
            crop_mask_img = mask_img[y1:y2, x1:x2]
            crop_mask_img = crop_mask_img * (1 - crop_mask) + crop_mask * color
            mask_img[y1:y2, x1:x2] = crop_mask_img

    return cv2.addWeighted(mask_img, mask_alpha, image, 1 - mask_alpha, 0)


def draw_comparison(img1, img2, name1, name2, fontsize=2.6, text_thickness=3):
    (tw, th), _ = cv2.getTextSize(text=name1, fontFace=cv2.FONT_HERSHEY_DUPLEX,
                                  fontScale=fontsize, thickness=text_thickness)
    x1 = img1.shape[1] // 3
    y1 = th
    offset = th // 5
    cv2.rectangle(img1, (x1 - offset * 2, y1 + offset),
                  (x1 + tw + offset * 2, y1 - th - offset), (0, 115, 255), -1)
    cv2.putText(img1, name1,
                (x1, y1),
                cv2.FONT_HERSHEY_DUPLEX, fontsize,
                (255, 255, 255), text_thickness)

    (tw, th), _ = cv2.getTextSize(text=name2, fontFace=cv2.FONT_HERSHEY_DUPLEX,
                                  fontScale=fontsize, thickness=text_thickness)
    x1 = img2.shape[1] // 3
    y1 = th
    offset = th // 5
    cv2.rectangle(img2, (x1 - offset * 2, y1 + offset),
                  (x1 + tw + offset * 2, y1 - th - offset), (94, 23, 235), -1)

    cv2.putText(img2, name2,
                (x1, y1),
                cv2.FONT_HERSHEY_DUPLEX, fontsize,
                (255, 255, 255), text_thickness)

    combined_img = cv2.hconcat([img1, img2])
    if combined_img.shape[1] > 3840:
        combined_img = cv2.resize(combined_img, (3840, 2160))

    return combined_img

def tfserving_model_pred(image,input_width,input_height):

    img_ = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    img_ = cv2.resize(img_, (input_width, input_height))
    img_ = img_ / 255.0
    img_data = img_[None].tolist()
    data = {"instances": img_data}
    # output_ = requests.post("http://172.20.112.102:9911/v1/models/yolov8:predict", json=data)
    output_ = requests.post("http://172.20.112.102:9921/v1/models/yolov8_rx:predict", json=data)
    output = json.loads(output_.content.decode('utf8'))["predictions"][0]
    output_det = np.array(output["output0"])
    output_mask = np.array(output["output1"])

    return output_det, output_mask

def tfserving_model_PIL_pred(image, input_width, input_height):
    img_ = image.resize((input_height, input_width))
    img_np = np.array(img_)/255.
    img_data = img_np[None].tolist()
    data = {"instances":img_data}
    output_ = requests.post("http://172.20.112.102:9911/v1/models/yolov8:predict", json=data)
    output = json.loads(output_.content.decode('utf8'))["predictions"][0]
    output_det = np.array(output["output0"])
    output_mask = np.array(output["output1"])
    
    return output_det, output_mask

def process_box_output(box_output,num_masks=32,conf_threshold=0.25,iou_threshold=0.7):

    predictions = np.squeeze(box_output).T
    num_classes = predictions.shape[1] - num_masks - 4

    scores = np.max(predictions[:, 4:4+num_classes], axis=1)
    predictions = predictions[scores > conf_threshold, :]
    scores = scores[scores > conf_threshold]

    if len(scores) == 0:
        return [], [], [], np.array([])

    box_predictions = predictions[..., :num_classes+4]
    mask_predictions = predictions[..., num_classes+4:]

    class_ids = np.argmax(box_predictions[:, 4:], axis=1)
    boxes = extract_boxes(box_predictions)
    indices = nms(boxes, scores, iou_threshold)

    return boxes[indices], scores[indices], class_ids[indices], mask_predictions[indices]

def process_mask_output(mask_predictions, mask_output,boxes,img_height=800,img_width=800):

    if mask_predictions.shape[0] == 0:
        return []

    mask_output = np.squeeze(mask_output)

    num_mask, mask_height, mask_width = mask_output.transpose(2,0,1).shape  # HWC --> CHW
    masks = sigmoid(mask_predictions @ mask_output.transpose(2,0,1).reshape((num_mask, -1)))
    masks = masks.reshape((-1, mask_height, mask_width))

    scale_boxes = rescale_boxes(boxes,
                                (img_height, img_width),
                                (mask_height, mask_width))

    mask_maps = np.zeros((len(scale_boxes), img_height, img_width))
    blur_size = (int(img_width / mask_width), int(img_height / mask_height))
    for i in range(len(scale_boxes)):

        scale_x1 = int(math.floor(scale_boxes[i][0]))
        scale_y1 = int(math.floor(scale_boxes[i][1]))
        scale_x2 = int(math.ceil(scale_boxes[i][2]))
        scale_y2 = int(math.ceil(scale_boxes[i][3]))

        x1 = int(math.floor(boxes[i][0]))
        y1 = int(math.floor(boxes[i][1]))
        x2 = int(math.ceil(boxes[i][2]))
        y2 = int(math.ceil(boxes[i][3]))

        scale_crop_mask = masks[i][scale_y1:scale_y2, scale_x1:scale_x2]
        crop_mask = cv2.resize(scale_crop_mask,
                            (x2 - x1, y2 - y1),
                            interpolation=cv2.INTER_CUBIC)

        crop_mask = cv2.blur(crop_mask, blur_size)

        crop_mask = (crop_mask > 0.5).astype(np.uint8)
        mask_maps[i, y1:y2, x1:x2] = crop_mask
        
    return mask_maps

def extract_boxes(box_predictions,input_height=640,input_width=640,img_height=800,img_width=800):
    boxes = box_predictions[:, :4]

    boxes = rescale_boxes(boxes,
                                (input_height, input_width),
                                (img_height, img_width))

    boxes = xywh2xyxy(boxes)

    boxes[:, 0] = np.clip(boxes[:, 0], 0, img_width)
    boxes[:, 1] = np.clip(boxes[:, 1], 0, img_height)
    boxes[:, 2] = np.clip(boxes[:, 2], 0, img_width)
    boxes[:, 3] = np.clip(boxes[:, 3], 0, img_height)
    return boxes

def draw_detections_out(image, boxes,scores,class_ids,draw_scores=True, mask_alpha=0.4):
    return draw_detections(image, boxes, scores,
                            class_ids, mask_alpha)

def draw_masks_out(image, boxes,scores,class_ids,mask_maps,draw_scores=True, mask_alpha=0.5):
    return draw_detections(image, boxes, scores,
                            class_ids, mask_maps, mask_alpha)


def rescale_boxes(boxes, input_shape, image_shape):
    input_shape = np.array([input_shape[1], input_shape[0], input_shape[1], input_shape[0]])
    boxes = np.divide(boxes, input_shape, dtype=np.float32)
    boxes *= np.array([image_shape[1], image_shape[0], image_shape[1], image_shape[0]])
    return boxes


# input_imgs = r"E:\pycharm_project\tfservingconvert\yolov8\model-yolo_lg\images/"
input_imgs = r"F:\data\light_group_rx_total\images\mmdet_mask\image\train/"

files = os.listdir(input_imgs)
# save_path = r"E:\pycharm_project\tfservingconvert\water_flowers\outputs\out_imgs2"
# save_path = r"E:\pycharm_project\tfservingconvert\yolov8\model-yolo_lg\tfserver_out"
save_path = r"F:\data\light_group_rx_total\images\mmdet_mask\image\tfserver_out/"

if os.path.exists(save_path):
    shutil.rmtree(save_path)
os.makedirs(save_path)
for file in files:
      # input_img = r"E:\pycharm_project\tfservingconvert\tf1.15v3\yc960xc1484.jpg"
    if file.split('.')[1] == "xml": continue
    input_img = input_imgs + file
    print(input_img)
    
    input_width = 640
    input_height = 640
    
    image = cv2.imread(input_img)
    pred_det, pred_mask =tfserving_model_pred(image, input_width, input_height)
    
    # image = Image.open(input_img)
    # pred_det, pred_mask =tfserving_model_PIL_pred(image, input_width, input_height)

    boxes, scores, class_ids, mask_pred = process_box_output(pred_det)
    mask_maps = process_mask_output(mask_pred,pred_mask,boxes)
    
    if isinstance(image,JpegImagePlugin.JpegImageFile):
        frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR) # 使用PIL image

    if isinstance(image,np.ndarray):
        frame = image.copy() # use cv2.imread()
    
    out_img = draw_masks_out(frame,boxes, scores, class_ids,mask_maps)
    cv2.imshow("output", out_img)
    cv2.imwrite(save_path + file, out_img)
    cv2.waitKey(0)
