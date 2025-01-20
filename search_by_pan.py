from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from io import BytesIO

from PIL import Image
import requests
import base64
import time
import os
import mysql.connector

# Flask app
app = Flask(__name__)

# Setup Chrome options
options = Options()
options.add_argument("--headless")  # Uncomment if running in headless mode
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

service = Service(executable_path='C:/Users/renuka/chromedriver.exe')

# Anticaptcha API Key
ANTI_CAPTCHA_API_KEY = "e3748137bbd8a34429089d049e35eef6"

# Aadhaar Verification URL
PAN_URL = "https://services.gst.gov.in/services/searchtpbypan"


def get_db_connection():
    return mysql.connector.connect(
        host='localhost',     
        user='root',  # MySQL username
        password='',  # MySQL password
        database='gst_details_schema'  # MySQL database name
    )

def save_data_to_db(pan_number,data):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert gst_data location data
    for gst_data in data['gst_data']:
        cursor.execute('''
        INSERT INTO pan_details (pan_number, S_NO, GSTIN_UIN, GSTIN_UIN_Status, state)
        VALUES (%s, %s, %s, %s, %s)
        ''', (pan_number, gst_data['S_NO'], gst_data['GSTIN_UIN'], gst_data['GSTIN_UIN_STATUS'], gst_data['STATE']))

    
    # Commit changes and close the connection
    conn.commit()
    cursor.close()
    conn.close()


# Solve CAPTCHA via AntiCaptcha
def solve_captcha_with_anticaptcha(captcha_image_path, max_attempts=3):
    for attempt in range(max_attempts):
        try:
            if not os.path.exists(captcha_image_path):
                raise FileNotFoundError(f"Captcha image not found at path: {captcha_image_path}")
            if os.path.getsize(captcha_image_path) == 0:
                raise ValueError("Captcha image file is empty.")
            
            # Open the image and convert it to PNG if necessary
            with open(captcha_image_path, 'rb') as captcha_file:
                captcha_image_data = captcha_file.read()
                captcha_image = Image.open(BytesIO(captcha_image_data))
                captcha_image_path_converted = 'uploads/captchas/captcha_image_converted.png'
                captcha_image.save(captcha_image_path_converted, 'PNG')
            
            # Re-encode the image as base64 after conversion
            with open(captcha_image_path_converted, 'rb') as captcha_file:
                captcha_image_data = captcha_file.read()
                captcha_image_base64 = base64.b64encode(captcha_image_data).decode('utf-8')
            
            # Create CAPTCHA task with AntiCaptcha API
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
            print("AntiCaptcha API Response:", response_json)
            if response_json.get("errorCode"):
                print(f"AntiCaptcha error code: {response_json['errorCode']}")
                print(f"AntiCaptcha error description: {response_json['errorDescription']}")
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
            print(f"Error solving CAPTCHA on attempt {attempt + 1}: {e}")
            if attempt < max_attempts - 1:
                print("Retrying CAPTCHA...")
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise Exception("Max CAPTCHA attempts reached. Please try again later.")


def check_pan_details(pan_number):
    """Automate PAN validity check."""
    driver = webdriver.Chrome(service=service, options=options)
    driver.get(PAN_URL)

    try:
        wait = WebDriverWait(driver, 100)

        # Enter PAN number
        pan_input = wait.until(
            EC.presence_of_element_located((By.ID, "for_gstin"))
        )
        pan_input.send_keys(pan_number)  
        print("PAN input located successfully")

        # Wait for the CAPTCHA image element to load
        captcha_image_element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "imgCaptcha"))
        )
        
        # Get the location and size of the CAPTCHA image
        location = captcha_image_element.location
        size = captcha_image_element.size
        
        # Take a screenshot of the full page
        driver.save_screenshot('uploads/captchas/full_page_screenshot.png')
        image = Image.open('uploads/captchas/full_page_screenshot.png')
        
        # Define the cropping box
        left, top = location['x'], location['y']
        right, bottom = left + size['width'], top + size['height']
        
        # Crop the CAPTCHA from the screenshot
        captcha_image = image.crop((left, top, right, bottom))
        captcha_image_path = 'uploads/captchas/captcha_image.png'
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

        # Click the Search Button
        search_button = wait.until(
            EC.element_to_be_clickable((By.ID, "lotsearch"))
        )
        search_button.click()
        print("Search button clicked successfully")

        # Check if CAPTCHA error message appears
        error_message = None
        try:
            error_message_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//span[@data-ng-if='searchtaxp.cap.$error.invalid_captcha'][contains(@class, 'err')]"))
            )
            error_message = error_message_element.text.strip()
        except:
            error_message = None

        if error_message:
            print(f"CAPTCHA Error: {error_message}. Retrying...")
            return {"message": error_message, "status": False}

        # Wait for the page to load completely and the search result to appear
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.XPATH, "//h4[contains(text(), 'Search Result based on PAN')]"))
        )
        print("Search result header found")

        time.sleep(10)

        # Extract all relevant data from the GST table
        gst_data = []
        gst_table = driver.find_element(By.XPATH, "//table[contains(@class, 'table tbl inv exp table-bordered ng-table')]")
        rows = gst_table.find_elements(By.TAG_NAME, "tr")
        for row in rows[1:]:  # Skip the header row
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 5:  # Ensure there are enough columns
                data_entry = {
                    "S_NO": cols[0].text.strip(),  # SNo.
                    "GSTIN_UIN": cols[1].text.strip(),  # GSTIN_UIN
                    "GSTIN_UIN_STATUS": cols[2].text.strip(),  # GSTIN_UIN_STATUS 
                    "STATE": cols[3].text.strip(),  # STATE 
                }
                gst_data.append(data_entry)

        data = {
            "gst_data": gst_data,  # Add all gst data to the result
        }
        
        # Save data to the database
        save_data_to_db(pan_number, data)

        return {"message": "GST details fetched successfully and data saved successfully", "status": True, "data": data}

    except Exception as e:
        print(f"Error: {e}")
        return {"message": f"Error occurred: {e}", "status": False}

    finally:
        driver.quit()

@app.route('/get-pan-details', methods=['POST'])
def get_pan_details():
    """API endpoint to validate PAN."""
    data = request.get_json()
    pan_number = data.get("pan_number")

    if not pan_number or len(pan_number) != 10:
        return jsonify({"message": "Invalid PAN number", "status": False}), 400

    result = check_pan_details(pan_number)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)

















































