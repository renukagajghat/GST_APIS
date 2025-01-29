from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image
from io import BytesIO
import requests
import base64
import time
import os
import traceback
import mysql.connector

# Flask app
app = Flask(__name__)

# AntiCaptcha API Key
ANTI_CAPTCHA_API_KEY = "68dc9b3228ebe691ade64c49499e69f4"

# Setup Chrome options
# Setup Chrome options
options = Options()
options.add_argument("--headless")  # Headless mode
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920x1080")  # Set window size for better rendering
options.add_argument("--start-maximized")  # Start the browser in maximized mode
options.add_argument("--disable-extensions")

# Path to the chromedriver
service = Service(executable_path='/usr/local/bin/chromedriver')

driver = webdriver.Chrome(service=service, options=options)
driver.set_window_size(1920, 1080)  # Ensure window size is set

# def get_db_connection():
#     return mysql.connector.connect(
#         host='localhost',     
#         user='root',
#         password='',
#         database='gst_details_schema'
#     )

# def save_data_to_db(gst_number, company_name):
#     conn = get_db_connection()
#     cursor = conn.cursor()
#     cursor.execute('''INSERT INTO gst_details (gst_number, company_name) VALUES (%s, %s)''', (gst_number, company_name))
#     conn.commit()
#     cursor.close()
#     conn.close()

def solve_captcha_with_anticaptcha(captcha_image_path, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            if not os.path.exists(captcha_image_path):
                raise FileNotFoundError(f"Captcha image not found at path: {captcha_image_path}")
            if os.path.getsize(captcha_image_path) == 0:
                raise ValueError("Captcha image file is empty.")
            
            with open(captcha_image_path, 'rb') as captcha_file:
                captcha_image_data = captcha_file.read()
                captcha_image = Image.open(BytesIO(captcha_image_data))
                captcha_image_path_converted = 'uploads/captcha/captcha_image_converted.png'
                captcha_image.save(captcha_image_path_converted, 'PNG')
            
            with open(captcha_image_path_converted, 'rb') as captcha_file:
                captcha_image_data = captcha_file.read()
                captcha_image_base64 = base64.b64encode(captcha_image_data).decode('utf-8')
            
            response = requests.post(
                'https://api.anti-captcha.com/createTask',
                json={
                    "clientKey": ANTI_CAPTCHA_API_KEY,
                    "task": {
                        "type": "ImageToTextTask",
                        "body": captcha_image_base64
                    }
                }
            )
            response_json = response.json()
            if response_json.get("errorCode"):
                raise Exception(f"AntiCaptcha API error: {response_json.get('errorDescription')}")
            
            task_id = response_json.get('taskId')
            if not task_id:
                raise ValueError("Failed to retrieve task ID.")
            
            while True:
                result_response = requests.post(
                    'https://api.anti-captcha.com/getTaskResult',
                    json={
                        "clientKey": ANTI_CAPTCHA_API_KEY,
                        "taskId": task_id
                    }
                )
                result_json = result_response.json()
                if result_json['status'] == 'ready':
                    return result_json['solution']['text']
                time.sleep(5)
        except Exception as e:
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
            else:
                raise Exception("Max CAPTCHA attempts reached.") from e

def check_gst_details(gst_number):
    driver = webdriver.Chrome(service=service, options=options)
    driver.get("https://services.gst.gov.in/services/searchtpbypan")

    try:
        wait = WebDriverWait(driver, 100)

        # Open "Search Taxpayer" dropdown
        search_taxpayer_dropdown = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[@class='dropdown-toggle' and contains(text(), 'Search Taxpayer')]"))
        )
        driver.execute_script("arguments[0].click();", search_taxpayer_dropdown)

        # Select "Search by GSTIN/UIN"
        search_by_gstin_option = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//ul[@class='dropdown-menu smenu searchtxp']/li/a[contains(@href, 'searchtp')]"))
        )
        driver.execute_script("arguments[0].click();", search_by_gstin_option)

        # Input GST number
        gst_input = wait.until(EC.presence_of_element_located((By.ID, "for_gstin")))
        gst_input.send_keys(gst_number)

        # Scroll to the bottom of the page to ensure full page is loaded
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")


        # Wait for the CAPTCHA image element to load
        captcha_image_element = WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.ID, "imgCaptcha"))
        )
        
        # Get the location and size of the CAPTCHA image
        location = captcha_image_element.location_once_scrolled_into_view
        size = captcha_image_element.size
            
        # Take a screenshot of the full page
        driver.save_screenshot('uploads/full_page_screenshot.png')
        image = Image.open('uploads/full_page_screenshot.png')
        
        # Define the cropping box
        left, top = location['x'], location['y']
        right, bottom = left + size['width'], top + size['height']
        
        # Crop the CAPTCHA from the screenshot
        captcha_image = image.crop((left, top, right, bottom))
        captcha_image_path = 'uploads/captcha_image.png'
        captcha_image.save(captcha_image_path)
        print(f"Cropped CAPTCHA image saved at {captcha_image_path}")
        
        # Solve the CAPTCHA using AntiCaptcha service
        captcha_text = solve_captcha_with_anticaptcha(captcha_image_path)
        print("Solved CAPTCHA text:", captcha_text)
        
        # Enter the CAPTCHA text
        captcha_input = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.ID, 'fo-captcha'))
        )
        captcha_input.clear()
        captcha_input.send_keys(captcha_text)
        time.sleep(1)

        search_button = wait.until(
            EC.element_to_be_clickable((By.ID, "lotsearch"))
        )
        search_button.click()

        # Wait for the table with the GST details to load
        try:
            # Look for the table with class `tbl-format`
            table_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "tbl-format"))
            )
            
            # Extract Legal Name of Business from the table
            legal_name_element = table_element.find_element(By.XPATH, "//div[@class='col-sm-4 col-xs-12']/p[strong[contains(text(), 'Legal Name of Business')]]/following-sibling::p")
            legal_name = legal_name_element.text.strip()

            # save_data_to_db(gst_number, legal_name)

            return {"message": "GST details fetched and data saved successfully", "status": True, "legal_name": legal_name}
        
        except Exception as e:
            # If the table is not found or there is no data, return failure status
            return {"message": "No data found", "status": False}

    except Exception as e:
        return {"message": f"Error occurred: {str(e)}", "status": False}

    finally:
        driver.quit()

@app.route('/get-gst-details', methods=['POST'])
def get_gst_details():
    data = request.get_json()
    gst_number = data.get("gst_number")
    if not gst_number or len(gst_number) != 15:
        return jsonify({"message": "Invalid GST number", "status": False}), 400
    result = check_gst_details(gst_number)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True, host="172.16.11.39", port=5002)
