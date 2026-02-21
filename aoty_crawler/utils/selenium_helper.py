# Utility functions for AOTY Crawler
# Selenium helpers and Cloudflare bypass utilities

import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


class SeleniumHelper:
    """
    Helper class for Selenium operations
    """
    
    def __init__(self, timeout=30, headless=True):
        self.timeout = timeout
        self.headless = headless
        self.driver = None
    
    def create_driver(self):
        """Create and configure Chrome driver"""
        options = uc.ChromeOptions()
        
        if self.headless:
            options.add_argument('--headless')
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Disable automation flags
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = uc.Chrome(options=options)
        self.driver.maximize_window()
        
        return self.driver
    
    def get_page_source(self, url):
        """Get page source with JavaScript execution"""
        if not self.driver:
            self.create_driver()
        
        try:
            self.driver.get(url)
            self.wait_for_page_load()
            
            # Add random delays to avoid detection
            time.sleep(random.uniform(2, 4))
            
            return self.driver.page_source
            
        except Exception as e:
            print(f"Error getting page source: {e}")
            return None
    
    def wait_for_page_load(self, timeout=None):
        """Wait for page to fully load"""
        if timeout is None:
            timeout = self.timeout
        
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except Exception as e:
            print(f"Timeout waiting for page load: {e}")
    
    def wait_for_element(self, selector, selector_type='css', timeout=None):
        """Wait for an element to be present"""
        if timeout is None:
            timeout = self.timeout
        
        try:
            if selector_type == 'css':
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            elif selector_type == 'xpath':
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, selector))
                )
            elif selector_type == 'id':
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.ID, selector))
                )
            else:
                element = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            
            return element
            
        except Exception as e:
            print(f"Error waiting for element: {e}")
            return None
    
    def close(self):
        """Close the driver"""
        if self.driver:
            self.driver.quit()
            self.driver = None


class CloudflareBypass:
    """
    Helper class for Cloudflare bypass
    """
    
    def __init__(self, driver):
        self.driver = driver
    
    def is_cloudflare_challenge(self):
        """Check if current page is a Cloudflare challenge"""
        if not self.driver:
            return False
        
        page_title = self.driver.title.lower()
        page_source = self.driver.page_source.lower()
        
        # Check for Cloudflare indicators
        cloudflare_indicators = [
            'cloudflare',
            'checking your browser',
            'ray id',
            'performance & security',
            'verify you are a human'
        ]
        
        return any(indicator in page_title or indicator in page_source 
                   for indicator in cloudflare_indicators)
    
    def wait_for_cloudflare(self, max_attempts=5, delay=3):
        """Wait for Cloudflare challenge to complete"""
        attempts = 0
        
        while attempts < max_attempts:
            if not self.is_cloudflare_challenge():
                return True
            
            print(f"Cloudflare challenge detected, waiting... (attempt {attempts + 1}/{max_attempts})")
            time.sleep(delay)
            attempts += 1
        
        return False
    
    def bypass_cloudflare(self, url, max_attempts=3):
        """Attempt to bypass Cloudflare protection"""
        for attempt in range(max_attempts):
            try:
                self.driver.get(url)
                
                # Wait for page to load
                time.sleep(random.uniform(3, 5))
                
                # Check if Cloudflare challenge is present
                if self.is_cloudflare_challenge():
                    if not self.wait_for_cloudflare():
                        print(f"Failed to bypass Cloudflare on attempt {attempt + 1}")
                        continue
                
                return True
                
            except Exception as e:
                print(f"Error during Cloudflare bypass attempt {attempt + 1}: {e}")
                time.sleep(random.uniform(2, 4))
        
        return False


def create_selenium_driver(headless=True, timeout=30):
    """Create a configured Selenium driver"""
    helper = SeleniumHelper(timeout=timeout, headless=headless)
    return helper.create_driver()


def get_page_with_selenium(url, headless=True, timeout=30):
    """Get page source using Selenium"""
    driver = None
    try:
        driver = create_selenium_driver(headless=headless, timeout=timeout)
        driver.get(url)
        
        # Wait for page load
        time.sleep(random.uniform(2, 4))
        
        return driver.page_source
        
    except Exception as e:
        print(f"Error getting page with Selenium: {e}")
        return None
        
    finally:
        if driver:
            driver.quit()


def is_cloudflare_blocked(page_source):
    """Check if page source indicates Cloudflare block"""
    if not page_source:
        return False
    
    page_lower = page_source.lower()
    
    # Check for Cloudflare indicators
    indicators = [
        'cloudflare',
        'checking your browser',
        'ray id',
        'performance & security',
        'verify you are a human',
        'access denied'
    ]
    
    return any(indicator in page_lower for indicator in indicators)
