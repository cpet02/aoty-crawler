# Middlewares for AOTY Crawler
# Custom middlewares for Selenium integration, retry logic, and request handling

import logging
import random
import time
from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
from scrapy.http import Request
from scrapy.spiders import Spider

logger = logging.getLogger(__name__)


class SeleniumMiddleware:
    """
    Middleware to handle JavaScript rendering using Selenium
    Especially useful for Cloudflare protection and dynamic content
    """
    
    def __init__(self, timeout=30, headless=True):
        self.timeout = timeout
        self.headless = headless
        self.driver = None
        
    @classmethod
    def from_crawler(cls, crawler):
        """Initialize middleware from crawler settings"""
        timeout = crawler.settings.getint('SELENIUM_TIMEOUT', 30)
        headless = crawler.settings.getbool('SELENIUM_HEADLESS', True)
        
        middleware = cls(timeout=timeout, headless=headless)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        
        return middleware
    
    def spider_opened(self, spider):
        """Initialize Selenium driver when spider opens"""
        spider.logger.info("Initializing Selenium driver...")
        self.driver = self._create_driver()
    
    def _create_driver(self):
        """Create and configure Chrome driver with undetected-chromedriver"""
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
        
        driver = uc.Chrome(options=options)
        driver.maximize_window()
        
        return driver
    
    def process_request(self, request, spider):
        """Process request through Selenium for JavaScript rendering"""
        # Only use Selenium for specific URLs or when explicitly requested
        if not request.meta.get('selenium', False):
            return None
        
        try:
            spider.logger.info(f"Rendering {request.url} with Selenium...")
            
            # Navigate to URL
            self.driver.get(request.url)
            
            # Wait for page to load
            self.driver.implicitly_wait(self.timeout)
            
            # Add random delays to avoid detection
            time.sleep(random.uniform(2, 4))
            
            # Get page source
            body = self.driver.page_source
            
            # Return HtmlResponse with rendered content
            return HtmlResponse(
                request.url,
                body=body,
                encoding='utf-8',
                status=200
            )
            
        except Exception as e:
            spider.logger.error(f"Selenium error for {request.url}: {e}")
            # Return original request if Selenium fails
            return None
    
    def spider_closed(self, spider):
        """Close Selenium driver when spider closes"""
        if self.driver:
            self.driver.quit()
            spider.logger.info("Selenium driver closed")


class RetryWithDelayMiddleware:
    """
    Custom retry middleware with exponential backoff and delays
    """
    
    def __init__(self, max_retry_times=3, retry_http_codes=None, download_delay=3):
        self.max_retry_times = max_retry_times
        self.retry_http_codes = retry_http_codes or [500, 502, 503, 504, 408, 429, 403]
        self.download_delay = download_delay
        
    @classmethod
    def from_crawler(cls, crawler):
        """Initialize middleware from crawler settings"""
        max_retry_times = crawler.settings.getint('RETRY_TIMES', 3)
        retry_http_codes = crawler.settings.getlist('RETRY_HTTP_CODES', [500, 502, 503, 504, 408, 429, 403])
        download_delay = crawler.settings.getfloat('DOWNLOAD_DELAY', 3)
        
        return cls(max_retry_times, retry_http_codes, download_delay)
    
    def process_response(self, request, response, spider):
        """Check response status and decide if retry is needed"""
        if response.status in self.retry_http_codes:
            retry_times = request.meta.get('retry_times', 0)
            
            if retry_times < self.max_retry_times:
                logger.info(f"Retrying {request.url} (attempt {retry_times + 1}/{self.max_retry_times})")
                
                # Calculate exponential backoff delay
                delay = self.download_delay * (2 ** retry_times) + random.uniform(0, 1)
                logger.info(f"Waiting {delay:.2f} seconds before retry...")
                
                # Wait before retrying
                time.sleep(delay)
                
                # Create new request
                new_request = request.copy()
                new_request.meta['retry_times'] = retry_times + 1
                new_request.dont_filter = True
                
                return new_request
        
        return response
    
    def process_exception(self, request, exception, spider):
        """Handle exceptions and schedule retry"""
        if isinstance(exception, (ConnectionError, TimeoutError)):
            retry_times = request.meta.get('retry_times', 0)
            
            if retry_times < self.max_retry_times:
                logger.info(f"Retrying {request.url} due to connection error (attempt {retry_times + 1}/{self.max_retry_times})")
                
                # Calculate exponential backoff delay
                delay = self.download_delay * (2 ** retry_times) + random.uniform(0, 1)
                time.sleep(delay)
                
                new_request = request.copy()
                new_request.meta['retry_times'] = retry_times + 1
                new_request.dont_filter = True
                
                return new_request


class RandomUserAgentMiddleware:
    """Middleware to rotate user agents"""
    
    def __init__(self):
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
    
    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.getbool('RANDOMIZE_USER_AGENT', True):
            raise NotConfigured
        return cls()
    
    def process_request(self, request, spider):
        user_agent = random.choice(self.user_agents)
        request.headers['User-Agent'] = user_agent
        spider.logger.debug(f"Using User-Agent: {user_agent}")


class RateLimitMiddleware:
    """Middleware to enforce rate limiting"""
    
    def __init__(self, delay=3, randomize=False):
        self.delay = delay
        self.randomize = randomize
        self.last_request_time = 0
    
    @classmethod
    def from_crawler(cls, crawler):
        delay = crawler.settings.getfloat('DOWNLOAD_DELAY', 3)
        randomize = crawler.settings.getbool('RANDOMIZE_DOWNLOAD_DELAY', True)
        return cls(delay, randomize)
    
    def process_request(self, request, spider):
        if self.last_request_time > 0:
            elapsed = time.time() - self.last_request_time
            wait_time = self.delay
            
            if self.randomize:
                wait_time = random.uniform(self.delay * 0.5, self.delay * 1.5)
            
            if elapsed < wait_time:
                sleep_time = wait_time - elapsed
                spider.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        return None
