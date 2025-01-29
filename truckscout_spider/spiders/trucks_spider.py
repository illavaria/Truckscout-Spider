import json
import os
import shutil

import scrapy
from bs4 import BeautifulSoup
import random
import urllib.request

from selenium import webdriver
from selenium.common import NoSuchElementException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from scrapy import signals
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class TrucksSpider(scrapy.Spider):
    name = "trucks_spider"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.driver = webdriver.Chrome()
        self.ads = []
        self.filename = "data.json"
        self.data_dir = "data"

        if os.path.exists(self.data_dir):
            shutil.rmtree(self.data_dir)
        os.makedirs(self.data_dir)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(TrucksSpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def start_requests(self):
        urls = ["https://www.truckscout24.de/transporter/gebraucht/kuehl-iso-frischdienst/renault"]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse)

    def parse(self, response):
        links = response.xpath('//a[@class="d-flex flex-column text-decoration-none mb-2"]/@href').getall()
        if links:
            random_link = random.choice(links)
            yield response.follow(random_link, callback=self.parse_details)

        next_page = response.xpath('//li[@class="page-item"]/a[not(contains(@class, "disabled"))]/@href').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_phone(self, response):
        self.driver.get(response.url)
        try:
            button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//button[@type="button" and contains(@class, "btn-primary")]'))
            )
            ActionChains(self.driver).move_to_element(button).click().perform()
            phone_element = WebDriverWait(self.driver, 7).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'tel:')]"))
            )
            phone_number = phone_element.text
        except NoSuchElementException:
            phone_number = ""

        return phone_number

    def download_images(self, image_urls, ad_folder):
        images_counter = 1
        for image_url in image_urls:
            file_name = f"{ad_folder}/img_{images_counter}.jpg"
            urllib.request.urlretrieve(image_url, file_name)
            images_counter += 1

    def parse_details(self, response):
        ad_id = response.url.split('/')[-1]
        ad_id = ''.join(ad_id.split('-')[1:])
        ad_folder = os.path.join(self.data_dir, ad_id)
        os.makedirs(ad_folder, exist_ok=True)

        image_urls = response.css("img.h-100.w-100::attr(src)").getall()[:3]
        self.download_images(image_urls, ad_folder)

        phone_number = self.parse_phone(response)
        soup = BeautifulSoup(response.body, "html.parser")
        name = (soup.find('b', class_="word-break").get_text() + ' ' +
                soup.find('b', class_="word-break").next_sibling.get_text().strip())

        price = response.css("div.fs-5.max-content.my-1.word-break.fw-bold::text").get(default='')
        price = int(price.split()[0].replace('.', '')) if price else 0
        mileage = response.xpath('//dl[dt[contains(text(), "Kilometerstand:")]]/dd/text()').get(default='')
        mileage = int(mileage.split()[0].replace('.', '')) if mileage else 0
        power = response.xpath('//dl[dt[contains(text(), "Leistung:")]]/dd/text()').get(default='')
        power = float(power.split()[0].replace(',', '.')) if power else 0
        color = response.xpath('//dl[dt[contains(text(), "Farbe:")]]/dd/text()').get(default='')
        description_text = response.css("div.col.beschreibung::text").getall()
        description = ' '.join([t.strip() for t in description_text])

        ad = {
            'id': int(ad_id),
            'title': name,
            'href': response.url,
            'price': price,
            'mileage': mileage,
            'color': color,
            'power': power,
            'description': description,
            'phone': phone_number,
        }

        self.ads.append(ad)

        yield ad

    def spider_closed(self, spider):
        full_path = os.path.join(self.data_dir, self.filename)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump({"ads": self.ads}, f, ensure_ascii=False, indent=4)
        spider.logger.info(f"{len(self.ads)} ads were written to file {full_path}")

        if self.driver:
            self.driver.quit()
