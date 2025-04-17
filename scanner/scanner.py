import cv2
import numpy as np
import os
import argparse
import itertools
import math
import sys  
from scipy.spatial import distance as dist
from pylsd.lsd import lsd
from pyimagesearch import transform
from pyimagesearch import imutils
# Fix: Using absolute path for imports from Structure
current_dir = os.path.dirname(os.path.abspath(__file__))
struct_dir = os.path.join(current_dir, 'Structure')
if struct_dir not in sys.path:
    sys.path.append(struct_dir)
from Structure.getConfig import config_
from DocScanner import Scanner
from Utils import *
import torch
import noteshrink

def sharpen_color_image(input_color_image, amount=2.5, sigma=3.5):
    """
    Sharpens a color image using the Unsharp Masking technique.

    Args:
        input_color_image (numpy.ndarray): The input BGR color image.
        amount (float): Controls the strength of the sharpening (e.g., 0.5 to 1.5).
                        Higher values mean stronger sharpening.
        sigma (float): Controls the radius/detail level of the sharpening.
                       Higher values affect coarser details, lower values affect finer details.
                       (e.g., 1.0 to 3.0).

    Returns:
        numpy.ndarray: The sharpened BGR color image. Returns the original image
                       if input is invalid or sharpening fails.
    """
    # --- Input Validation ---
    if input_color_image is None or input_color_image.size == 0:
        print("Warning: Sharpening received an empty image.")
        return input_color_image
    if len(input_color_image.shape) != 3 or input_color_image.shape[2] != 3:
        print("Warning: Sharpening expects a 3-channel color image.")
        return input_color_image
    if input_color_image.dtype != np.uint8:
        # Attempt to convert if possible, otherwise return original
        try:
            input_color_image = np.clip(input_color_image, 0, 255).astype(np.uint8)
        except ValueError:
             print("Warning: Could not convert input image to uint8 for sharpening.")
             return input_color_image

    # --- Sharpening Logic (Unsharp Masking) ---
    sharpened_image = input_color_image # Default to original if parameters are invalid
    if amount > 0 and sigma > 0:
        try:
            # 1. Create a blurred version of the image
            # (0, 0) kernel size lets GaussianBlur calculate it based on sigma
            blurred = cv2.GaussianBlur(input_color_image, (0, 0), sigma)

            # 2. Calculate the sharpened image using addWeighted
            # Formula: sharpened = original * (1 + amount) + blurred * (-amount)
            sharpened_image = cv2.addWeighted(input_color_image, 1.0 + amount, blurred, -amount, 0)

            # Ensure the result is clipped back to the valid [0, 255] range for uint8
            # addWeighted might produce values outside this range before clipping.
            # We don't need explicit clipping here as addWeighted often handles saturation,
            # but it's good practice if implementing manually. Ensure dtype remains uint8.
            # If needed: sharpened_image = np.clip(sharpened_image, 0, 255)

        except cv2.error as e:
             print(f"Error during OpenCV sharpening operation: {e}. Returning original image.")
             sharpened_image = input_color_image # Revert to original on error
        except Exception as e:
             print(f"An unexpected error occurred during sharpening: {e}. Returning original image.")
             sharpened_image = input_color_image # Revert to original on error

    return sharpened_image

def apply_white_magic(img):
    """
    Applies a 'white magic' effect to the image, brightening the background
    and enhancing contrast, similar to CamScanner.

    Args:
        img: Input BGR image (the warped document).

    Returns:
        BGR image with the effect applied.
    """
    # 1. Simple Automatic White Balance based on brightest pixels
    img_lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(img_lab)

    l_flat = l_channel.flatten()
    non_white_pixels = l_flat[l_flat < 254]
    if len(non_white_pixels) == 0:
         l_thresh = np.percentile(l_flat, 95) if len(l_flat) > 0 else 200
    else:
         l_thresh = np.percentile(non_white_pixels, 95)

    paper_pixels_mask = l_channel >= l_thresh
    paper_pixels = img[paper_pixels_mask]

    if paper_pixels.shape[0] < 10:
        print("Warning: Not enough 'paper white' pixels found for precise white balance.")
        avg_b, avg_g, avg_r = (200, 200, 200)
    else:
        avg_b = np.mean(paper_pixels[:, 0])
        avg_g = np.mean(paper_pixels[:, 1])
        avg_r = np.mean(paper_pixels[:, 2])

    max_scale = 3.0
    scale_b = min(255.0 / (avg_b + 1e-5), max_scale)
    scale_g = min(255.0 / (avg_g + 1e-5), max_scale)
    scale_r = min(255.0 / (avg_r + 1e-5), max_scale)

    img_b, img_g, img_r = cv2.split(img)
    balanced_b = np.clip(img_b * scale_b, 0, 255)
    balanced_g = np.clip(img_g * scale_g, 0, 255)
    balanced_r = np.clip(img_r * scale_r, 0, 255)
    balanced_img = cv2.merge([balanced_b, balanced_g, balanced_r]).astype(np.uint8)

    balanced_lab = cv2.cvtColor(balanced_img, cv2.COLOR_BGR2LAB)
    l_balanced, a_balanced, b_balanced = cv2.split(balanced_lab)

    l_enhanced = cv2.convertScaleAbs(l_balanced, alpha=1.1, beta=2)

    enhanced_lab = cv2.merge([l_enhanced, a_balanced, b_balanced])
    contrast_enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    img_hsv = cv2.cvtColor(contrast_enhanced_img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(img_hsv)
    s_boosted = np.clip(s * 1.25, 0, 255).astype(np.uint8)
    img_hsv_boosted = cv2.merge([h, s_boosted, v])
    final_img = cv2.cvtColor(img_hsv_boosted, cv2.COLOR_HSV2BGR)
    final_img = sharpen_color_image(final_img)

    return final_img


class DocScanner(object):
    """An image scanner"""

    def __init__(self, MIN_QUAD_AREA_RATIO=0.25, MAX_QUAD_ANGLE_RANGE=40):
        """
        Args:
            MIN_QUAD_AREA_RATIO (float): A contour will be rejected if its corners
                do not form a quadrilateral that covers at least MIN_QUAD_AREA_RATIO
                of the original image. Defaults to 0.25.
            MAX_QUAD_ANGLE_RANGE (int):  A contour will also be rejected if the range
                of its interior angles exceeds MAX_QUAD_ANGLE_RANGE. Defaults to 40.
        """
        self.MIN_QUAD_AREA_RATIO = MIN_QUAD_AREA_RATIO
        self.MAX_QUAD_ANGLE_RANGE = MAX_QUAD_ANGLE_RANGE

    def filter_corners(self, corners, min_dist=20):
        """Filters corners that are within min_dist of others"""
        def predicate(representatives, corner):
            return all(dist.euclidean(representative, corner) >= min_dist
                       for representative in representatives)

        filtered_corners = []
        for c in corners:
            if predicate(filtered_corners, c):
                filtered_corners.append(c)
        return filtered_corners

    def angle_between_vectors_degrees(self, u, v):
        """Returns the angle between two vectors in degrees"""
        norm_u = np.linalg.norm(u)
        norm_v = np.linalg.norm(v)
        if norm_u == 0 or norm_v == 0:
            return 0.0

        dot_product = np.dot(u, v)
        cos_theta = np.clip(dot_product / (norm_u * norm_v), -1.0, 1.0)

        return np.degrees(math.acos(cos_theta))

    def get_angle(self, p1, p2, p3):
        """
        Returns the angle between the line segment from p2 to p1
        and the line segment from p2 to p3 in degrees
        """
        a = np.array(p1, dtype=float)
        b = np.array(p2, dtype=float)
        c = np.array(p3, dtype=float)

        avec = a - b
        cvec = c - b

        return self.angle_between_vectors_degrees(avec, cvec)

    def angle_range(self, quad):
        """
        Returns the range between max and min interior angles of quadrilateral.
        The input quadrilateral must be a numpy array with vertices ordered clockwise
        starting with the top left vertex. Shape should be (4, 1, 2) or (4, 2).
        """
        if quad.shape == (4, 1, 2):
             points = quad.reshape(4, 2)
        elif quad.shape == (4,2):
             points = quad
        else:
             raise ValueError("Input quadrilateral has unexpected shape: {}".format(quad.shape))

        tl, tr, br, bl = points

        angle_tr = self.get_angle(tl, tr, br)
        angle_br = self.get_angle(tr, br, bl)
        angle_bl = self.get_angle(br, bl, tl)
        angle_tl = self.get_angle(bl, tl, tr)

        angles = [angle_tr, angle_br, angle_bl, angle_tl]
        angles = [a for a in angles if not np.isnan(a)]
        if not angles:
             return np.inf
        return np.ptp(angles)

    def get_corners(self, img):
        """
        Returns a list of corners ((x, y) tuples) found in the input image. With proper
        pre-processing and filtering, it should output at most 10 potential corners.
        This is a utility function used by get_contours. The input image is expected
        to be rescaled and Canny filtered prior to be passed in.
        """
        if len(img.shape) == 3:
             gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
             gray_img = img
        if gray_img.dtype != np.uint8:
             gray_img = np.clip(gray_img, 0, 255).astype(np.uint8)

        lines = lsd(gray_img)

        corners = []
        if lines is not None:
            lines = lines.squeeze().astype(np.int32).tolist()
            horizontal_lines_canvas = np.zeros(img.shape[:2], dtype=np.uint8)
            vertical_lines_canvas = np.zeros(img.shape[:2], dtype=np.uint8)
            for line in lines:
                x1, y1, x2, y2, _ = line
                if abs(x2 - x1) > abs(y2 - y1):
                    (pt1_x, pt1_y), (pt2_x, pt2_y) = sorted(((x1, y1), (x2, y2)), key=lambda pt: pt[0])
                    cv2.line(horizontal_lines_canvas, (max(pt1_x - 5, 0), pt1_y), (min(pt2_x + 5, img.shape[1] - 1), pt2_y), 255, 2)
                else:
                    (pt1_x, pt1_y), (pt2_x, pt2_y) = sorted(((x1, y1), (x2, y2)), key=lambda pt: pt[1])
                    cv2.line(vertical_lines_canvas, (pt1_x, max(pt1_y - 5, 0)), (pt2_x, min(pt2_y + 5, img.shape[0] - 1)), 255, 2)

            processed_lines = []

            (contours, hierarchy) = cv2.findContours(horizontal_lines_canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:2]

            horizontal_lines_canvas = np.zeros(img.shape[:2], dtype=np.uint8)
            for contour in contours:
                if len(contour) < 1: continue
                x, y, w, h = cv2.boundingRect(contour)
                contour_points = contour.reshape(-1, 2)
                if w > h:
                     min_x_idx = np.argmin(contour_points[:, 0])
                     max_x_idx = np.argmax(contour_points[:, 0])
                     pt1 = tuple(contour_points[min_x_idx])
                     pt2 = tuple(contour_points[max_x_idx])
                     pt1 = (int(pt1[0]), int(pt1[1]))
                     pt2 = (int(pt2[0]), int(pt2[1]))

                     processed_lines.append((pt1, pt2))
                     cv2.line(horizontal_lines_canvas, pt1, pt2, 1, 1)
                     corners.append(pt1)
                     corners.append(pt2)

            (contours, hierarchy) = cv2.findContours(vertical_lines_canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:2]

            vertical_lines_canvas = np.zeros(img.shape[:2], dtype=np.uint8)
            for contour in contours:
                 if len(contour) < 1: continue
                 x, y, w, h = cv2.boundingRect(contour)
                 contour_points = contour.reshape(-1, 2)
                 if h >= w:
                      min_y_idx = np.argmin(contour_points[:, 1])
                      max_y_idx = np.argmax(contour_points[:, 1])
                      pt1 = tuple(contour_points[min_y_idx])
                      pt2 = tuple(contour_points[max_y_idx])
                      pt1 = (int(pt1[0]), int(pt1[1]))
                      pt2 = (int(pt2[0]), int(pt2[1]))

                      processed_lines.append((pt1, pt2))
                      cv2.line(vertical_lines_canvas, pt1, pt2, 1, 1)
                      corners.append(pt1)
                      corners.append(pt2)

            intersection_canvas = horizontal_lines_canvas + vertical_lines_canvas
            corners_y, corners_x = np.where(intersection_canvas == 2)
            corners += list(zip(corners_x, corners_y))

        corners = self.filter_corners(corners)
        return corners

    def is_valid_contour(self, cnt, IM_WIDTH, IM_HEIGHT):
        """Returns True if the contour satisfies all requirements set at instantitation"""
        is_four_corners = len(cnt) == 4
        if not is_four_corners:
            return False

        area = cv2.contourArea(cnt)
        if area <= 0: return False

        has_min_area = area > IM_WIDTH * IM_HEIGHT * self.MIN_QUAD_AREA_RATIO
        if not has_min_area:
            return False

        try:
            if cnt.shape[1] == 1:
                 pts = cnt.reshape(-1, 2).astype(np.float32)
            else:
                 pts = cnt.astype(np.float32)

            ordered_cnt = transform.order_points(pts)
            angle_r = self.angle_range(ordered_cnt)

            is_angle_ok = angle_r < self.MAX_QUAD_ANGLE_RANGE
            return is_angle_ok
        except ValueError as e:
            print(f"Warning: ValueError calculating angle range: {e}")
            return False
        except Exception as e:
             print(f"Warning: Error calculating angle range: {e}")
             return False

    def get_contour(self, rescaled_image):
        """
        Returns a numpy array of shape (4, 2) containing the vertices of the four corners
        of the document in the image. It considers the corners returned from get_corners()
        and uses heuristics to choose the four corners that most likely represent
        the corners of the document. If no corners were found, or the four corners represent
        a quadrilateral that is too small or convex, it returns the original four corners
        of the image.
        """

        MORPH = 9
        CANNY = 84

        IM_HEIGHT, IM_WIDTH, _ = rescaled_image.shape

        gray = cv2.cvtColor(rescaled_image, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (7,7), 0)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT,(MORPH,MORPH))
        dilated = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

        edged = cv2.Canny(dilated, 0, CANNY)
        test_corners = self.get_corners(edged)

        approx_contours = []

        if len(test_corners) >= 4:
            quads = []
            corner_combinations = itertools.combinations(test_corners, 4)
            count = 0
            max_combinations_to_check = 2000

            for quad_coords in corner_combinations:
                count += 1
                if count > max_combinations_to_check:
                     break

                points = np.array(quad_coords, dtype="float32")
                ordered_points = transform.order_points(points)
                contour_points = ordered_points.reshape(4, 1, 2).astype("int32")

                if self.is_valid_contour(contour_points, IM_WIDTH, IM_HEIGHT):
                     quads.append({'contour': contour_points, 'area': cv2.contourArea(contour_points)})

            if quads:
                 quads = sorted(quads, key=lambda q: q['area'], reverse=True)
                 best_quad_from_corners = quads[0]['contour']
                 approx_contours.append(best_quad_from_corners)

        (cnts, hierarchy) = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:10]

        for c in cnts:
            peri = cv2.arcLength(c, True)
            for eps_factor in [0.02, 0.04, 0.06, 0.08, 0.1]:
                epsilon = eps_factor * peri
                approx = cv2.approxPolyDP(c, epsilon, True)
                if len(approx) == 4 and self.is_valid_contour(approx, IM_WIDTH, IM_HEIGHT):
                    is_new = True
                    for existing_cnt in approx_contours:
                         if abs(cv2.contourArea(approx) - cv2.contourArea(existing_cnt)) < 0.05 * IM_WIDTH * IM_HEIGHT :
                              is_new = False
                              break
                    if is_new:
                         approx_contours.append(approx)
                         break
            if len(approx_contours) > 5:
                 break

        if not approx_contours:
            print("Warning: No valid document contour found. Using image boundaries.")
            screenCnt = np.array([
                [IM_WIDTH - 1, 0],
                [IM_WIDTH - 1, IM_HEIGHT - 1],
                [0, IM_HEIGHT - 1],
                [0, 0]
            ], dtype="float32")
        else:
            screenCnt = max(approx_contours, key=cv2.contourArea)
            screenCnt = transform.order_points(screenCnt.reshape(4, 2).astype(np.float32))

        return screenCnt.reshape(4, 2)

    def scan(self, image_path):
        """Performs the main scanning process for a single image."""

        RESCALED_HEIGHT = 500.0
        OUTPUT_DIR = args["output"]
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        image = cv2.imread(image_path)
        if image is None:
            print(f"Error: Could not read image {image_path}")
            return

        orig_h, orig_w = image.shape[:2]
        if orig_h == 0:
            print(f"Error: Invalid image height for {image_path}")
            return

        ratio = orig_h / RESCALED_HEIGHT
        orig = image.copy()
        rescaled_image = imutils.resize(image, height=int(RESCALED_HEIGHT))

        screenCnt = self.get_contour(rescaled_image)

        warped = transform.four_point_transform(orig, screenCnt * ratio)

        warped_color_enhanced = apply_white_magic(warped)

        basename = os.path.basename(image_path)
        filename_base, filename_ext = os.path.splitext(basename)
        color_output_path = os.path.join(OUTPUT_DIR, f"{filename_base}_magic_color{filename_ext}")
        try:
            cv2.imwrite(color_output_path, warped_color_enhanced)
            print(f"Saved enhanced color image to {color_output_path}")
            
            
            noteshrink_args = noteshrink.get_argument_parser().parse_args([
                color_output_path,
                '--output', OUTPUT_DIR,
                '-q'
            ])
            noteshrink.notescan_main(noteshrink_args)
            
            noteshrink_output = os.path.join(OUTPUT_DIR, f"{filename_base}_magic_color_enhanced.png")
            old_noteshrink_output = os.path.join(OUTPUT_DIR, f"{filename_base}_magic_color_enhanced.png")
            if os.path.exists(old_noteshrink_output):
                os.rename(old_noteshrink_output, noteshrink_output)
                
        except Exception as e:
            print(f"Error in processing: {e}")

        from Utils import EnhancePaper

        # VARIANT 1: Direct approach - always use warped image
        paper_bw_direct = EnhancePaper(warped)
        filename_base, filename_ext = os.path.splitext(basename)
        bw_direct_output_path = os.path.join(OUTPUT_DIR, f"{filename_base}_BW_direct{filename_ext}")
        try:
            if paper_bw_direct is not None and paper_bw_direct.size > 0:
                cv2.imwrite(bw_direct_output_path, paper_bw_direct)
                print(f"Processed and saved direct B&W image to {bw_direct_output_path}")
            else:
                print(f"Error: Direct B&W image processing failed to produce valid output")
        except Exception as e:
            print(f"Error saving direct B&W image {bw_direct_output_path}: {e}")

        # VARIANT 2: Smart approach with multiple fallbacks
        try:
            # First attempt: ScannSavedImage with original image
            # Fix: Use absolute path to the model file
            model_path = os.path.join(current_dir, 'Structure', 'Scanner-Detector.pth')
            scanner = Scanner(model_path, config_, device=torch.device('cpu'))
            paper, org = ScannSavedImage(str(image_path), scanner, False)
            
            # Verify we got a valid image
            if paper is not None and paper.size > 0:
                print("Document detection successful with original image")
                paper_bw = EnhancePaper(paper)
            else:
                print("First detection attempt failed, trying with warped image...")
                # Second attempt: ScannSavedImage with already warped image
                try:
                    # Save warped image temporarily
                    temp_warped_path = os.path.join(OUTPUT_DIR, f"{filename_base}_temp_warped{filename_ext}")
                    cv2.imwrite(temp_warped_path, warped)
                    
                    # Try document detection on the warped image
                    paper2, _ = ScannSavedImage(temp_warped_path, scanner, False)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_warped_path):
                        os.remove(temp_warped_path)
                    
                    if paper2 is not None and paper2.size > 0:
                        print("Document detection successful with warped image")
                        paper_bw = EnhancePaper(paper2)
                    else:
                        # Third fallback: Use warped directly
                        print("Second detection attempt failed, using warped image directly")
                        paper_bw = EnhancePaper(warped)
                except Exception as e2:
                    print(f"Error in second document detection attempt: {e2}, using warped image directly")
                    paper_bw = EnhancePaper(warped)
                    
        except Exception as e:
            print(f"Error in first document detection attempt: {e}, using warped image directly")
            paper_bw = EnhancePaper(warped)

        bw_output_path = os.path.join(OUTPUT_DIR, f"{filename_base}_BW{filename_ext}")
        try:
            # Final check to ensure we have a valid image before writing
            if paper_bw is not None and paper_bw.size > 0:
                cv2.imwrite(bw_output_path, paper_bw)
                print(f"Processed and saved B&W image to {bw_output_path}")
            else:
                print(f"Error: B&W image processing failed to produce valid output")
        except Exception as e:
            print(f"Error saving B&W image {bw_output_path}: {e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scan documents from images.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--images", help="Directory of images to be scanned")
    group.add_argument("--image", help="Path to single image to be scanned")
    ap.add_argument("--output", default='output', 
        help="Output directory path (default: 'output')")

    args = vars(ap.parse_args())

    im_dir = args["images"]
    im_file_path = args["image"]
    output_dir = args["output"]

    scanner = DocScanner()

    valid_formats = [".jpg", ".jpeg", ".jp2", ".png", ".bmp", ".tiff", ".tif"]
    get_ext = lambda f: os.path.splitext(f)[1].lower()

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    if im_file_path:
        if os.path.exists(im_file_path) and get_ext(im_file_path) in valid_formats:
            print(f"\nScanning single image: {im_file_path}")
            scanner.scan(im_file_path)
        elif not os.path.exists(im_file_path):
            print(f"Error: Image file not found: {im_file_path}")
        else:
            print(f"Error: Invalid image format for {im_file_path}. Supported formats: {valid_formats}")

    elif im_dir:
        if os.path.isdir(im_dir):
            print(f"\nScanning images in directory: {im_dir}")
            im_files = [f for f in os.listdir(im_dir) if os.path.isfile(os.path.join(im_dir, f)) and get_ext(f) in valid_formats]
            if not im_files:
                print(f"No valid images found in directory: {im_dir}")
            else:
                print(f"Found {len(im_files)} images to scan.")
                for im_name in im_files:
                    full_im_path = os.path.join(im_dir, im_name)
                    print(f"\n--- Processing: {im_name} ---")
                    scanner.scan(full_im_path)
        else:
            print(f"Error: Directory not found: {im_dir}")

    print("\nScanning process finished.")

