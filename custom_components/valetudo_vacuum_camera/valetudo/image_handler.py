# Image Handler Module
# Collection of routines to extract data from the received json.
# It returns values and images relative to the Map Data extrapolated from the vacuum json.

import logging
import math

import numpy as np
from PIL import Image, ImageDraw

_LOGGER = logging.getLogger(__name__)

from custom_components.valetudo_vacuum_camera.utils.colors import (
    color_charger,
    color_move,
    color_wall,
    color_robot,
    color_home_background,
    color_ext_background,
    color_grey,
)


class MapImageHandler(object):
    def __init__(self):
        self.img_size = None
        self.crop_area = None
        self.crop_img_size = None
        self.img_base_layer = None
        self.frame_number = 0
        self.path_pixels = None
        self.robot_pos = None
        self.charger_pos = None
        self.json_id = None
        self.go_to = None

    @staticmethod
    def sublist(lst, n):
        return [lst[i : i + n] for i in range(0, len(lst), n)]

    @staticmethod
    def sublist_join(lst, n):
        arr = np.array(lst)
        num_windows = len(lst) - n + 1
        result = [arr[i : i + n].tolist() for i in range(num_windows)]
        return result

    @staticmethod
    def find_points_entities(json_obj, entity_dict=None):
        if entity_dict is None:
            entity_dict = {}
        if isinstance(json_obj, dict):
            if json_obj.get("__class") == "PointMapEntity":
                entity_type = json_obj.get("type")
                if entity_type:
                    entity_dict.setdefault(entity_type, []).append(json_obj)
            for value in json_obj.values():
                MapImageHandler.find_points_entities(value, entity_dict)
        elif isinstance(json_obj, list):
            for item in json_obj:
                MapImageHandler.find_points_entities(item, entity_dict)
        return entity_dict

    @staticmethod
    def find_paths_entities(json_obj, entity_dict=None):
        if entity_dict is None:
            entity_dict = {}
        if isinstance(json_obj, dict):
            if json_obj.get("__class") == "PathMapEntity":
                entity_type = json_obj.get("type")
                if entity_type:
                    entity_dict.setdefault(entity_type, []).append(json_obj)
            for value in json_obj.values():
                MapImageHandler.find_paths_entities(value, entity_dict)
        elif isinstance(json_obj, list):
            for item in json_obj:
                MapImageHandler.find_paths_entities(item, entity_dict)
        return entity_dict

    @staticmethod
    def find_zone_entities(json_obj, entity_dict=None):
        if entity_dict is None:
            entity_dict = {}
        if isinstance(json_obj, dict):
            if json_obj.get("__class") == "PolygonMapEntity":
                entity_type = json_obj.get("type")
                if entity_type:
                    entity_dict.setdefault(entity_type, []).append(json_obj)
            for value in json_obj.values():
                MapImageHandler.find_zone_entities(value, entity_dict)
        elif isinstance(json_obj, list):
            for item in json_obj:
                MapImageHandler.find_zone_entities(item, entity_dict)
        return entity_dict

    @staticmethod
    def create_empty_image(width, height, background_color):
        # Create the empty image array
        image_array = np.zeros((height, width, 4), dtype=np.uint8)
        # Set the background color
        image_array[:, :, 0] = background_color[0]  # Set red channel
        image_array[:, :, 1] = background_color[1]  # Set green channel
        image_array[:, :, 2] = background_color[2]  # Set blue channel
        image_array[:, :, 3] = background_color[3]   # Set alpha channel to 255 (fully opaque)

        return image_array

    @staticmethod
    def from_json_to_image(layer, data, pixel_size, color):
        # Create an array of zeros for the image
        image_array = layer
        # Draw rectangles for each point in data
        for x, y, z in data:
            for i in range(z):
                col = (x + i) * pixel_size
                row = y * pixel_size
                image_array[row : row + pixel_size, col : col + pixel_size] = color
        # Convert the image array to a PIL image
        return image_array

    def crop_array(self, image_array, crop_percentage):
        """Crops a numpy array and returns the cropped image and scale factor."""
        center_x = image_array.shape[1] // 2
        center_y = image_array.shape[0] // 2
        crop_size = int(min(center_x, center_y) * crop_percentage / 100)
        cropbox = (
            center_x - crop_size,
            center_y - crop_size,
            center_x + crop_size,
            center_y + crop_size,
        )
        self.crop_area = cropbox
        _LOGGER.debug("Crop Box data: %s", self.crop_area)
        cropped = image_array[cropbox[1] : cropbox[3], cropbox[0] : cropbox[2]]
        self.crop_img_size = (cropped.shape[1], cropped.shape[0])
        _LOGGER.debug("Crop image size: %s", self.crop_img_size)
        return cropped

    @staticmethod
    def draw_robot(layers, x, y, angle, fill):
        tmpimg = Image.fromarray(np.zeros_like(layers), mode="RGBA")
        draw = ImageDraw.Draw(tmpimg)
        # Outline colour from fill colour
        outline = ((fill[0]) // 2, (fill[1]) // 2, (fill[2]) // 2)
        radius = 25  # Radius of the vacuum constant
        r_scaled = radius // 11  # Offset scale for placement of the objects.
        # Draw the robot outline
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=fill, outline=outline
        )
        # Draw bin cover
        r_cover = r_scaled * 12
        angle = angle - 80
        a1 = ((angle + 80) - 80) / 180 * math.pi
        a2 = ((angle + 80) + 80) / 180 * math.pi
        x1 = int(x - r_cover * math.sin(a1))
        y1 = int(y + r_cover * math.cos(a1))
        x2 = int(x - r_cover * math.sin(a2))
        y2 = int(y + r_cover * math.cos(a2))
        draw.line((x1, y1, x2, y2), fill=outline, width=1)
        # draw Lidar
        lidar_angle = np.deg2rad(
            angle + 170
        )  # Convert angle to radians and adjust for LIDAR orientation
        lidar_x = int(x + 15 * np.cos(lidar_angle))  # Calculate LIDAR x-coordinate
        lidar_y = int(y + 15 * np.sin(lidar_angle))  # Calculate LIDAR y-coordinate
        r_lidar = r_scaled * 3  # Scale factor for the lidar
        draw.ellipse(
            (
                lidar_x - r_lidar,
                lidar_y - r_lidar,
                lidar_x + r_lidar,
                lidar_y + r_lidar,
            ),
            fill=outline,
            width=5,
        )
        # Draw Button
        r_button = r_scaled * 1  # scale factor of the button
        butt_x = int(x - 20 * np.cos(lidar_angle))  # Calculate the button x-coordinate
        butt_y = int(y - 20 * np.sin(lidar_angle))  # Calculate the button y-coordinate
        draw.ellipse(
            (
                butt_x - r_button,
                butt_y - r_button,
                butt_x + r_button,
                butt_y + r_button,
            ),
            fill=outline,
            width=1,
        )
        # Convert the PIL image back to a Numpy array
        return np.array(tmpimg)

    @staticmethod
    def draw_battery_charger(layers, x, y, color):
        charger_width = 10
        charger_height = 20
        # Get the starting and ending indices of the charger rectangle
        start_row = y - charger_height // 2
        end_row = start_row + charger_height
        start_col = x - charger_width // 2
        end_col = start_col + charger_width
        # Fill in the charger rectangle with the specified color
        layers[start_row:end_row, start_col:end_col] = color
        return layers

    @staticmethod
    def draw_go_to_flag(layer, center):
        # Define flag color
        flag_color = (0, 255, 0, 127)  # RGBA color (green)
        # Define flag size and position
        flag_size = 40
        y1 = center[1] - flag_size // 2
        x2 = center[0] + flag_size // 2
        y2 = y1 + (flag_size // 4)
        # Define pole end position
        y3 = center[1] + flag_size // 2
        # Create an Image object from the layer array
        tmp_img = Image.fromarray(layer)
        # Draw flag on layer
        draw = ImageDraw.Draw(tmp_img)
        draw.polygon([center[0], center[1], x2, y2, center[0], y1], fill=flag_color)
        # Draw flag pole
        pole_width = 3
        pole_color = (0, 0, 255, 255)  # RGBA color (blue)
        draw.rectangle(
            (center[0] - pole_width // 2, y1, center[0] + pole_width // 2, y3),
            fill=pole_color,
        )
        # Convert the Image object back to the numpy array
        layer = np.array(tmp_img)
        return layer

    @staticmethod
    def draw_zone_clean(coordinates, layers, color):
        # Create an Image object from the numpy array
        tmp_img = Image.fromarray(np.zeros_like(layers))
        outline = ((color[0]) // 2, (color[1]) // 2, (color[2]) // 2)
        # Draw rectangle on the image
        draw = ImageDraw.Draw(tmp_img)
        tot_zones = len(coordinates) - 1
        while tot_zones >= 0:
            tot_zones = tot_zones - 1
            draw.polygon(
                (coordinates[tot_zones]["points"]), fill=color, outline=outline, width=1
            )
        # Convert the Image object back to the numpy array
        tmp_img = layers + tmp_img
        out_layer = np.array(tmp_img)
        # free memory
        del tmp_img, tot_zones, draw, outline
        return out_layer

    @staticmethod
    def draw_lines(arr, coords, width, color):
        for coord in coords:
            # Use Bresenham's line algorithm to get the coordinates of the line pixels
            x0, y0 = coord[0]
            try:
                x1, y1 = coord[1]
            except IndexError:
                x1 = x0
                y1 = y0
            dx = abs(x1 - x0)
            dy = abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx - dy
            line_pixels = []
            while True:
                line_pixels.append((x0, y0))
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 > -dy:
                    err -= dy
                    x0 += sx
                if e2 < dx:
                    err += dx
                    y0 += sy

            # Iterate over the line pixels and draw filled rectangles with the specified width
            for pixel in line_pixels:
                x, y = pixel
                for i in range(width):
                    for j in range(width):
                        if 0 <= x + i < arr.shape[0] and 0 <= y + j < arr.shape[1]:
                            arr[y + i, x + j] = color
        return arr

    def get_image_from_json(self, m_json):
        if m_json is not None:
            # Reading and splitting the Json form Valetudo
            size_x = int(m_json["size"]["x"])
            size_y = int(m_json["size"]["y"])
            self.img_size = {
                "x": size_x,
                "y": size_y,
                "centre": [(size_x // 2), (size_y // 2)],
            }

            self.json_id = m_json["metaData"]["nonce"]

            # Predicted path if any
            predicted_pat2 = None
            predicted_path = self.find_paths_entities(m_json, None)
            predicted_path = predicted_path.get("predicted_path")
            if predicted_path:
                predicted_path = predicted_path[0]["points"]
                predicted_path = self.sublist(predicted_path, 2)
                predicted_pat2 = self.sublist_join(predicted_path, 2)

            # Zone cleaning area if any
            zone_clean = self.find_zone_entities(m_json, None)

            # Saerching the "points" robot, charger and go_to
            entity_dict = self.find_points_entities(m_json, None)
            robot_pos = entity_dict.get("robot_position")
            robot_position = robot_pos[0]["points"]
            robot_position_angle = robot_pos[0]["metaData"]["angle"]
            self.robot_pos = {
                "x": robot_position[0],
                "y": robot_position[1],
                "angle": robot_position_angle,
            }
            charger_pos = entity_dict.get("charger_location")
            if charger_pos:
                charger_pos = charger_pos[0]["points"]
                self.charger_pos = {
                    "x": charger_pos[0],
                    "y": charger_pos[1],
                }
            go_to = entity_dict.get("go_to_target")

            """Calibration data of the result image
            Size X and Y give the result as calculated in the robot.
            Pixel size is defined for lidar resolution and image points location. """

            pixel_size = int(m_json["pixelSize"])
            flour_pixels = m_json["layers"][0]["compressedPixels"]
            walls_pixels = m_json["layers"][1]["compressedPixels"]
            path_pixels = m_json["entities"][0]["points"]

            # Formatting the data arrays for Numpy
            flour_pixels = self.sublist(flour_pixels, 3)
            walls_pixels = self.sublist(walls_pixels, 3)
            path_pixels = self.sublist(path_pixels, 2)
            path_pixel2 = self.sublist_join(path_pixels, 2)
            if self.frame_number == 0:
                _LOGGER.debug("Drawing image background")
                # Create the base Numpy array
                img_np_array = self.create_empty_image(size_x,size_y,color_ext_background)
                # Numpy array pixels positions and colours computation
                img_np_array = self.from_json_to_image(
                    img_np_array, flour_pixels, pixel_size, color_home_background
                )
                # If there is a zone clean we draw it now.
                if zone_clean:
                    zones_clean = zone_clean.get("active_zone")
                    img_np_array = self.draw_zone_clean(
                        zones_clean, img_np_array, (0, 0, 255, 64)
                    )
                # Drawing walls
                img_np_array = img_np_array + self.from_json_to_image(
                    img_np_array, walls_pixels, pixel_size, color_wall
                )
                # Drawing base / Battery Charger
                if charger_pos:
                    img_np_array = self.draw_battery_charger(
                        img_np_array, charger_pos[0], charger_pos[1], color_charger
                    )
                self.img_base_layer = img_np_array # Store flour, walls and charger combined NP array.
                self.frame_number += 1
            else:
                img_np_array = self.img_base_layer
                _LOGGER.debug("Frame nuber %s", self.frame_number)
                self.frame_number += 1
                if self.frame_number > 5:
                    self.frame_number = 0
            if go_to:  # if we have a goto position draw the flag end point.
                img_np_array = self.draw_go_to_flag(
                    img_np_array, (go_to[0]["points"][0], go_to[0]["points"][1])
                )
            # finally let´s add the robot layer adding predicted path if available
            if predicted_pat2:
                img_np_array = self.draw_lines(
                    img_np_array, predicted_pat2, 2, color_grey
                )
            img_np_array = self.draw_lines(img_np_array, path_pixel2, 5, color_move)
            img_np_array = img_np_array + self.draw_robot(
                img_np_array,
                robot_position[0],
                robot_position[1],
                robot_position_angle,
                color_robot,
            )
            # The image is cropped 75% so that the last layer is smaller to be sent.
            img_np_array = self.crop_array(img_np_array, 25)
            # Conversion of NP array to PIL image
            pil_img = Image.fromarray(img_np_array, mode="RGBA")
            return pil_img
        else:
            return None

    def get_robot_position(self):
        return self.robot_pos

    def get_charger_position(self):
        return self.charger_pos

    def get_img_size(self):
        return self.img_size

    def get_json_id(self):
        return self.json_id

    def get_calibration_data(self, rotation_angle):
        calibration_data = []

        # Calculate the calibration points in the vacuum coordinate system
        vacuum_points = [
            {"x": self.crop_area[0], "y": self.crop_area[1]},  # Top-left corner 0
            {"x": self.crop_area[2], "y": self.crop_area[1]},  # Top-right corner 1
            {"x": self.crop_area[2], "y": self.crop_area[3]},  # Bottom-right corner 2
            {"x": self.crop_area[0], "y": self.crop_area[3]},  # Bottom-left corner (optional)3
        ]

        # Define the map points (fixed)
        map_points = [
            {"x": 0, "y": 0},  # Top-left corner 0
            {"x": self.crop_img_size[0], "y": 0},  # Top-right corner 1
            {
                "x": self.crop_img_size[0],
                "y": self.crop_img_size[1],
            },  # Bottom-right corner 2
            {"x": 0, "y": self.crop_img_size[1]},  # Bottom-left corner (optional) 3
        ]

        # Rotate the vacuum points based on the rotation angle
        if rotation_angle == 90:
            vacuum_points = [vacuum_points[1], vacuum_points[2], vacuum_points[3], vacuum_points[0]]
        elif rotation_angle == 180:
            vacuum_points = [vacuum_points[2], vacuum_points[3], vacuum_points[0], vacuum_points[1]]
        elif rotation_angle == 270:
            vacuum_points = [vacuum_points[3], vacuum_points[0], vacuum_points[1], vacuum_points[2]]

        # Create the calibration data for each point
        for vacuum_point, map_point in zip(vacuum_points, map_points):
            calibration_point = {"vacuum": vacuum_point, "map": map_point}
            calibration_data.append(calibration_point)

        return calibration_data
