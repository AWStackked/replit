from flask import Flask, request, render_template, send_file
import os
from werkzeug.utils import secure_filename
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import pandas as pd
from typing import Dict, List
import logging
import time
from bs4 import BeautifulSoup
import csv
from utils import find_and_click_image
import pyautogui
import re
from selenium.webdriver.common.action_chains import ActionChains

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

class MapScraper:
    def __init__(self, username: str, password: str, use_proxy: bool = False, zyte_api_key: str = None):
        self.zoom = True
        self.map_center_x = None
        self.map_center_y = None
        self.is_found_once = False
        self.marker_image_clicked = False
        self.username = username
        self.password = password
        self.base_url = "https://login.digitalmapcentral.com/MemberPages/Login.aspx?ReturnUrl=/memberpages/default.aspx?ma=groceryanchored&ma=groceryanchored"
        self.driver = None
        self.use_proxy = use_proxy
        self.zyte_api_key = zyte_api_key
        self.headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-encoding': 'gzip, deflate, br, zstd',
            'accept-language': 'en-GB,en;q=0.9',
            'sec-ch-ua': '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36'
        }
        self.setup_driver()
        self.property_data = {}

    def setup_driver(self):
        """Initialize the Chrome WebDriver with appropriate options"""
        chrome_options = Options()
        # if self.use_proxy and self.zyte_api_key:
        #     proxy = f"http://{self.zyte_api_key}:@proxy.zyte.com:8011"
        #     chrome_options.add_argument(f'--proxy-server={proxy}')
            # logger.info("Configured Zyte Smart Proxy")
        
        # Disable password save popup and geolocation
        chrome_options.add_experimental_option('prefs', {
            'credentials_enable_service': False,
            'profile': {
                'password_manager_enabled': False
            },
            'profile.default_content_setting_values.notifications': 2,  # Block notifications
            'profile.default_content_setting_values.geolocation': 2  # Allow geolocation
        })
        
        # Add headers and other configurations
        for key, value in self.headers.items():
            chrome_options.add_argument(f'--header={key}:{value}')
        
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')  # Hide automation
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # For Replit, specify the ChromeDriver path
        self.driver = webdriver.Chrome(
            executable_path='/usr/lib/chromium-browser/chromedriver',
            options=chrome_options
        )
        
        # Maximize browser window
        self.driver.maximize_window()
        logger.info("Maximized browser window")
        
        self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": self.headers['user-agent']})
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.implicitly_wait(10)
    
    def login(self) -> bool:
        """
        Login to Digital Map Central
        Returns:
            bool: True if login successful, False otherwise
        """
        try:
            logger.info("Attempting to login to Digital Map Central")
            self.driver.get(self.base_url)
            
            # Wait for cookies/session to be set
            WebDriverWait(self.driver, 10).until(
                lambda driver: driver.get_cookie('ASP.NET_SessionId') is not None
            )
            
            # Wait for username field and enter credentials
            username_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "ctl00_ctl00_MainContentPlaceHolder_MainContent_LoginUser_UserName"))
            )
            username_input.send_keys(self.username)
            
            # Enter password
            password_input = self.driver.find_element(By.ID, "ctl00_ctl00_MainContentPlaceHolder_MainContent_LoginUser_Password")
            password_input.send_keys(self.password)
            
            # Click login button
            login_button = self.driver.find_element(By.ID, "ctl00_ctl00_MainContentPlaceHolder_MainContent_LoginUser_LoginButton")
            login_button.click()
            
            # Wait for login to complete
            WebDriverWait(self.driver, 2).until(
                lambda driver: driver.current_url != self.base_url
            )
            
            logger.info("Successfully logged in")
            
            # Try to find and click the Pendo guide close button
            try:
                close_button = WebDriverWait(self.driver, 2).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "_pendo-close-guide"))
                )
                close_button.click()
                logger.info("Closed Pendo guide")
            except Exception as e:
                logger.info("No Pendo guide found or already closed, continuing...")
            
            # Find and click the LightBox Vision link
            try:
                lightbox_link = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.AppLinkSingleButton[href*='LandVision']"))
                )
                lightbox_link.click()
                logger.info("Clicked on LightBox Vision link")
            except Exception as e:
                logger.error(f"Failed to click LightBox Vision link: {str(e)}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            return False
    
    def scrape_zipcode(self, zipcode: str) -> Dict:
        """
        Scrape data for a single zipcode
        Args:
            zipcode: The zipcode to scrape
        Returns:
            Dictionary containing scraped data
        """
        try:
            if not self.login():
                raise Exception("Failed to login")
                
            # Placeholder for actual scraping logic
            pass
            
        except Exception as e:
            logger.error(f"Error scraping zipcode {zipcode}: {str(e)}")
            return {}
    
    def save_to_excel(self, data: List[Dict], output_file: str):
        """Save scraped data to Excel file"""
        try:
            df = pd.DataFrame(data)
            df.to_excel(output_file, index=False)
            logger.info(f"Data successfully saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving to Excel: {str(e)}")
    
    def __del__(self):
        """Cleanup method to close the browser"""
        if self.driver:
            self.driver.quit()

    def search_coordinates(self, coordinates):
        """
        Search for each coordinate pair in the provided list
        Args:
            coordinates_list: List of coordinate pairs (latitude, longitude)
        """
        try:
            # Find and clear the search box
            search_box = WebDriverWait(self.driver, 7).until(
                EC.presence_of_element_located((By.ID, "searchInputBox"))
            )
            # Wait for filter panel to appear
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "filterDiv_Panel"))
            )
            search_box.clear()
            
            # Enter coordinates
            search_box.click()
            time.sleep(1)
            search_box.send_keys(coordinates)
            time.sleep(2)
            
            search_box.send_keys(Keys.RETURN)
            # Wait for 5 seconds after each search
            logger.info(f"Searching coordinates: {coordinates}")
            time.sleep(5)
            self.click_on_marker()
            time.sleep(5)
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.no-stripes tbody[data-surfedit='tableField_group']"))
                )
            except Exception as e:
                return
            balloon_div = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, "balloonDivId"))
            )

            print("==============data found=================")
            # Get the HTML content of the balloon div
            html_content = balloon_div.get_attribute('innerHTML')
            
            # Extract and process the property data
            self.extract_property_data(html_content)
                
        except Exception as e:
            logger.error(f"Error in search_coordinates method ========================== {e}")
            raise e
        
    def click_on_marker(self):
        if not self.map_center_x or not self.map_center_y:
            try:
                map_element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "Microsoft.Maps.Imagery.Aerial"))
                )
            except Exception as e:
                print(f"Could not locate map element with ID 'Microsoft.Maps.Imagery.Aerial': {e}")
                try:
                    map_element = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "Microsoft.Maps.Imagery.LiteAerial"))
                    )
                    print("Falling back to 'Microsoft.Maps.Imagery.LiteAerial' ID.")
                except Exception as e2:
                    pass
            
            # Get the map element's position and size
            map_location = map_element.location
            map_size = map_element.size
            print(f"Map element location: {map_location}, size: {map_size}")
            if self.zoom:
                zoom_in = self.driver.find_element(By.CLASS_NAME, "plus_in")
                print("==============zoom_in=================",zoom_in)
                time.sleep(2)
                zoom_in.click()
                time.sleep(2)
                self.zoom = False
            self.map_center_x = map_location['x'] + (map_size['width'] // 2)
            self.map_center_y = map_location['y'] + (map_size['height'] // 2)
            overlay_canvas = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "labelCanvasId"))
            )
            print("==============overlay canvas=================",overlay_canvas)
            overlay_height = int(overlay_canvas.get_attribute("height"))
            height_diff = overlay_height - self.map_center_y
            print("==============height_diff=================",height_diff)
            print(f"Clicking at dynamic map center for first record: ({self.map_center_x}, {self.map_center_y})")

        # Click the center 3 times
        time.sleep(2)
        for i in range(1):
            pyautogui.click(x=self.map_center_x+0, y=self.map_center_y+115, clicks=1, interval=1, button='left')
            time.sleep(2)
            pyautogui.moveTo(self.map_center_x-105, self.map_center_y+30)
            time.sleep(2)
            
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table.no-stripes tbody[data-surfedit='tableField_group']"))
                )
                break
            except Exception as e:
                pass

            time.sleep(1)

    def extract_property_data(self, html_content):
        """Extract property data from HTML and append to a single CSV"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        self.property_data = {}
        
        # Extract site address
        panel_descriptor = soup.find('h6', class_='panel_descriptor')
        if panel_descriptor:
            self.property_data['Site Address'] = panel_descriptor.text.strip()
        
        # Find all table rows
        rows = soup.find_all('tr')
        # Create a mapping of field labels to data keys
        field_mapping = {
            'Site Address': 'Site Address',
            'Parcel No. (APN)': 'Parcel No.',
            'Building Area': 'Building Area (sqft)',
            'Lot Area': 'Lot Area (Acres)',
            'Year Built': 'Year Built',
            'Owner (Assessor)': 'Owner 1',
            'Owner Address (Assessor)': 'Combined Owner Address',
            'Last Market Sale': 'Last Market Sale',
            'Buyer Name': 'Buyer Name',
            'Seller Name': 'Seller Name',
            'Document No.': 'Document No.',
            'Loan Amount': 'Loan Amount',
            'Lender': 'Lender',
            'Legal Information': 'Legal Information',
            'Subdivision': 'Subdivision',
            'Legal Lot': 'Legal Lot',
            'Legal Block': 'Legal Block', 
            'Land Use Cat.': 'Land Use Category',
            'Land Use Desc.': 'Land Use Description',
            'Lot Area (Assessor)': 'Lot Area Assessor',
            'Lot Area (Calc.)': 'Lot Area Calculated',
            'Adj. Lots Owned': 'Adjacent Lots Owned',
            'Building Area': 'Building Area',
            'Building/Lot Ratio': 'Building Lot Ratio',
            'No. of Units': 'Number of Units',
            'No. of Stories': 'Number of Stories',
            'Year Built': 'Year Built',
            'Zoning (Assessor)': 'Zoning',
            'Traffic': 'Traffic',
            'Bedrooms': 'Bedrooms',
            'Total Rooms': 'Total Rooms',
            'Baths': 'Baths',
            'Construction': 'Construction',
            'Heat Type': 'Heat Type',
            'Air Conditioning': 'Air Conditioning',
            'Roof Type': 'Roof Type',
            'Roof Material': 'Roof Material',
            'Style': 'Style',
            'Parking Spaces': 'Parking Spaces',
            'Fireplace': 'Fireplace',
            'Garage Type': 'Garage Type',
            'Basement': 'Basement'
        }
        
        # Extract data from rows
        for row in rows:
            label_cell = row.find('td', attrs={'data-surfedit': 'tableField_label'})
            value_cell = row.find('td', attrs={'data-surfedit': 'tableField_value'})
            
            if label_cell and value_cell:
                label = label_cell.text.strip()
                value = value_cell.text.strip()
                
                # Map the field label to the correct data key
                if label in field_mapping:
                    key = field_mapping[label]
                    
                    # Special handling for specific fields
                    if key == 'Building Area (sqft)':
                        value = value.replace('SF', '').strip()
                    elif key == 'Lot Area (Acres)':
                        acres_match = re.search(r'\(([\d.]+)\s*ACRES\)', value)
                        if acres_match:
                            value = acres_match.group(1)
                    elif key == 'Combined Owner Address':
                        addr_parts = value.split(',')
                        if len(addr_parts) >= 2:
                            self.property_data['Owner Address 1'] = addr_parts[0].strip()
                            city_state_zip = addr_parts[1].strip().split()
                            if len(city_state_zip) >= 3:
                                self.property_data['Owner City'] = ' '.join(city_state_zip[:-2])
                                self.property_data['Owner State'] = city_state_zip[-2]
                                self.property_data['Owner Zip'] = city_state_zip[-1]
                    
                    self.property_data[key] = value

        # Extract demographics data
        demographics_section = soup.find('li', id=lambda x: x and x.startswith('Demographics'))
        if demographics_section:
            demo_rows = demographics_section.find_all('tr')
            for row in demo_rows:
                label_cell = row.find('td', attrs={'data-surfedit': 'tableField_label'})
                value_cell = row.find('td', attrs={'data-surfedit': 'tableField_value'})
                
                if label_cell and value_cell:
                    label = label_cell.text.strip()
                    value = value_cell.text.strip()
                    
                    if label == 'Population':
                        self.property_data['Total 3mi Population'] = value
                    elif label == 'Median HH Income':
                        self.property_data['Average 3mi $HHI'] = value.replace('$', '').replace(',', '')
                    elif label == 'Median Age':
                        self.property_data['Average 3mi Age'] = value
        
        return self.property_data

def read_coordinates_from_csv(input_file: str) -> List[Dict]:
    """Read data from Before.csv"""
    try:
        df = pd.read_csv(input_file)
        records = []
        for _, row in df.iterrows():
            if pd.notna(row['Lat/Long']):
                coords = row['Lat/Long'].strip()
                record = {
                    'coordinates': coords,
                    'Property_name': row['Property name'],
                    'Address_1': row['Address 1'],
                    'City': row['City'],
                    'State': row['State'],
                    'Zip_code': row['Zip code'],
                    'County': row['County'],
                    'Listed_Price': row['Listed Price'],
                    'Listed_NOI': row['Listed NOI*'],
                    'List_CAP': row['List CAP'],
                    'Broker_List': row['Broker List'],
                    'Owner_Company': row['Owner.Company'],
                    'Owner_Address': row['Owner.Address 1'],
                    'Owner_City': row['Owner.City'],
                    'Owner_State': row['Owner.State'],
                    'Owner_Zip': row['Owner.Zip code']
                }
                records.append(record)
        return records
    except Exception as e:
        logger.error(f"Error reading from Before.csv: {str(e)}")
        return []

def merge_with_after_data(scraped_data: Dict, coordinates: str, before_data: Dict, remarks: str = "") -> Dict:
    """Merge scraped data with Before.csv data and existing After.csv data"""
    try:
        merged_data = {
            'Cleaned Lat/Long': coordinates,
            'Property name': before_data['Property_name'],
            'Address 1': before_data['Address_1'],
            'City': before_data['City'],
            'State': before_data['State'],
            'Zip code': before_data['Zip_code'],
            'County': before_data['County'],
            'Listed Price': before_data['Listed_Price'],
            'Listed NOI*': before_data['Listed_NOI'],
            'List CAP': before_data['List_CAP'],
            'Broker List': before_data['Broker_List'],
            'Owner.Company': before_data['Owner_Company'],
            'Owner.Address 1': before_data['Owner_Address'],
            'Owner.City': before_data['Owner_City'],
            'Owner.State': before_data['Owner_State'],
            'Owner.Zip code': before_data['Owner_Zip'],
            'Lat/Long': coordinates,
            'Site Address': scraped_data.get('Site Address', ''),
            'Parcel No.': scraped_data.get('Parcel No.', ''),
            'Building Area (sqft)': scraped_data.get('Building Area', ''),
            'Lot Area (Acres)': scraped_data.get('Lot Area (Acres)', ''),
            'Year Built': scraped_data.get('Year Built', ''),
            'Owner 1': scraped_data.get('Owner 1', ''),
            'Owner 2': '',
            'Combined Owner Address': scraped_data.get('Combined Owner Address', ''),
            'Owner Address 1': scraped_data.get('Owner Address 1', ''),
            'Owner City': '',
            'Owner State': '',
            'Owner Zip': '',
            'Last Transfer': '',
            'Last Market Sale': scraped_data.get('Last Market Sale', ''),
            'Last Sale Price': scraped_data.get('Last Sale Price', ''),
            'Buyer Name': scraped_data.get('Buyer Name', ''),
            'Seller Name': scraped_data.get('Seller Name', ''),
            'Document No.': scraped_data.get('Document No.', ''),
            'Loan Amount': scraped_data.get('Loan Amount', ''),
            'Lender': scraped_data.get('Lender', ''),
            'Total 3mi Population': scraped_data.get('Total 3mi Population', ''),
            'Average 3mi $HHI': scraped_data.get('Average 3mi $HHI', ''),
            'Average 3mi Age': scraped_data.get('Average 3mi Age', ''),
            'Land Use': scraped_data.get('Land Use Description', ''),
            'Legal Information': scraped_data.get('Legal Information', ''),
            'Owner (Assessor)': scraped_data.get('Owner (Assessor)', ''),
            'Owner Occupied': scraped_data.get('Owner Occupied', ''),
            'Property Tax': scraped_data.get('Property Tax', ''),
            'Total Assessed Value': scraped_data.get('Total Assessed Value', ''),
            'Assessed Improvement Value': scraped_data.get('Assessed Improvement Value', ''),
            'Assessed Land Value': scraped_data.get('Assessed Land Value', ''),
            'Assessed Year': scraped_data.get('Assessed Year', ''),
            'Improvement Percentage': scraped_data.get('Building Lot Ratio', ''),
            'Tax Year': scraped_data.get('Tax Year', ''),
            'Zoning': scraped_data.get('Zoning', ''),
            'Remarks': remarks
        }
        return merged_data
    except Exception as e:
        logger.error(f"Error merging data: {str(e)}")
        return {}

def process_csv(input_file: str, output_file: str, test_limit: int = None):
    username = "intern2"
    password = "Optics33"
    zyte_api_key = "dfabad9b113a412791890bb1ae8c12c3"
    
    records = read_coordinates_from_csv(input_file)
    
    if not records:
        logger.error("No records found in input CSV")
        return False
    
    if test_limit and test_limit > 0:
        records = records[:test_limit]
        logger.info(f"Running with {test_limit} records")
    
    scraper = MapScraper(
        username=username,
        password=password,
        use_proxy=True,
        zyte_api_key=zyte_api_key
    )
    
    if scraper.login():
        time.sleep(10)
        
        if os.path.exists(output_file):
            os.remove(output_file)
        pyautogui.scroll(10)
        
        for record in records:
            try:
                coordinates = record['coordinates']
                remarks = ""
                
                scraper.search_coordinates(coordinates)
                
                if not scraper.property_data:
                    remarks = "Unable to find or click marker image so skipping"
                print("====================", scraper.property_data, "scraped data --------")
                merged_data = merge_with_after_data(scraper.property_data, coordinates, record, remarks)
                scraper.property_data = {}
                
                with open(output_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=merged_data.keys())
                    if f.tell() == 0:
                        writer.writeheader()
                    writer.writerow(merged_data)
                
                logger.info(f"Successfully processed coordinates: {coordinates}")
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error processing record: {str(e)}")
                return False
    return True

# Flask routes
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('upload.html', error='No file part')
        file = request.files['file']
        if file.filename == '':
            return render_template('upload.html', error='No selected file')
        if file and file.filename.endswith('.csv'):
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(input_path)
            
            output_filename = f"{filename[:-4]}done.csv"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            success = process_csv(input_path, output_path)
            
            if success and os.path.exists(output_path):
                return send_file(output_path, as_attachment=True)
            else:
                return render_template('upload.html', error='Processing failed')
    return render_template('upload.html')

upload_html = """
<!DOCTYPE html>
<html>
<head>
    <title>CSV Processor</title>
</head>
<body>
    <h1>Upload CSV File</h1>
    <form method="post" enctype="multipart/form-data">
        <input type="file" name="file" accept=".csv">
        <input type="submit" value="Process">
    </form>
    {% if error %}
        <p style="color: red;">{{ error }}</p>
    {% endif %}
</body>
</html>
"""

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists('templates'):
        os.makedirs('templates')
    with open('templates/upload.html', 'w') as f:
        f.write(upload_html)
    app.run(host='0.0.0.0', port=8080)
