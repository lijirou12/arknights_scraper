import os
import time
import re
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
# from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from tqdm import tqdm
import sys

# 设置爬取图片的网址
base_url = "https://prts.wiki/index.php?title=%E7%89%B9%E6%AE%8A:%E6%90%9C%E7%B4%A2&limit=500&profile=images&search=%E7%AB%8B%E7%BB%98"

# 重定义请求头
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def fetch_html(url, driver):
    """使用Selenium获取动态加载的网页内容"""
    try:
        driver.get(url)
        # 使用显式等待，直到搜索结果容器出现，最多等待30秒
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "searchresults"))
        )
        return driver.page_source
    except Exception as e:
        print(f"使用Selenium获取网页 {url} 时发生错误: {e}")
        return None

def parse_image_links(html):
    soup = BeautifulSoup(html, "html.parser")
    search_results = soup.find("div", class_="searchresults")
    image_links = []
    if not search_results:
        print("未能找到搜索结果容器，请检查网页结构或URL。")
        # 为了调试目的，保存页面内容以便分析
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("已保存当前页面内容到 debug_page.html，用于调试分析")
        return image_links
        
    # 打印找到的结果数量
    results = search_results.find_all("li", class_="mw-search-result")
    print(f"找到 {len(results)} 个搜索结果")
    
    # 遍历所有搜索结果
    for i, result in enumerate(results):
        # 查找包含文件链接的元素
        links = result.find_all("a", href=True)
        for link in links:
            href = link.get("href")
            # 检查链接是否指向文件页面且包含"立绘"关键词
            if href and "/w/%E6%96%87%E4%BB%B6:" in href and "%E7%AB%8B%E7%BB%98" in href:
                # 确保是完整的URL
                if href.startswith("https://prts.wiki"):
                    image_page_url = href
                else:
                    image_page_url = "https://prts.wiki" + href
                # 检查是否已添加此链接
                if image_page_url not in image_links:
                    image_links.append(image_page_url)
                    if len(image_links) <= 10:  # 只打印前10个链接以避免输出过多
                        print(f"找到图片链接: {image_page_url}")
                break  # 每个结果只取一个链接
    
    if len(image_links) > 10:
        print(f"... 还有 {len(image_links) - 10} 个链接")
    print(f"总共提取到 {len(image_links)} 个图片链接")
    return image_links

def download_image(image_page_url, headers, progress_bar=None):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            image_page_response = requests.get(image_page_url, headers=headers, timeout=20)
            image_page_response.raise_for_status()
            image_page_response.encoding = "utf-8"
            
            image_page_soup = BeautifulSoup(image_page_response.text, "html.parser")
            
            # 从标题中提取完整文件名
            heading = image_page_soup.find("h1", id="firstHeading")
            if not heading:
                if progress_bar:
                    progress_bar.update(1)
                return False
                
            full_filename = heading.get_text(strip=True).replace("文件:", "")
            
            # 提取干员名称和皮肤编号
            char_name = ""
            skin_number = ""
            
            # 解析文件名，例如："立绘 令 2.png"
            match = re.match(r"立绘[ _](.+?)(?:[_ ](.*?))?\.png", full_filename)
            if match:
                char_name = match.group(1).strip()
                skin_number = match.group(2) if match.group(2) else ""
            else:
                # 如果标准格式不匹配，尝试其他方法
                char_name_match = re.search(r"([^(]+)", full_filename)
                if char_name_match:
                    char_name = char_name_match.group(1).replace("立绘", "").strip()
                    
            if not char_name or char_name.startswith("预备干员"):
                if progress_bar:
                    progress_bar.update(1)
                return True  # 跳过非干员图片，不计为失败

            char_name = re.sub(r'[\\/*?:"<>|]', "", char_name)
            skin_number = re.sub(r'[\\/*?:"<>|]', "", skin_number) if skin_number else ""

            # 创建干员专属文件夹
            char_folder = os.path.join(os.getcwd(), char_name)
            if not os.path.exists(char_folder):
                os.makedirs(char_folder)

            # 构建文件名
            if skin_number:
                image_name = f"{char_name} {skin_number}.png"
            else:
                image_name = f"{char_name}.png"
                
            image_path = os.path.join(char_folder, image_name)
            
            # 检查文件是否已经存在
            if os.path.exists(image_path):
                if progress_bar:
                    progress_bar.update(1)
                return True

            full_image_link = image_page_soup.find("div", class_="fullImageLink", id="file")
            if full_image_link:
                image_link = full_image_link.find("a")
                if image_link and image_link.get("href"):
                    image_download_url = image_link.get("href")
                    
                    image_download_response = requests.get(image_download_url, headers=headers, timeout=25)
                    image_download_response.raise_for_status()
                    with open(image_path, "wb") as f:
                        f.write(image_download_response.content)
                        
                    if progress_bar:
                        progress_bar.update(1)
                    return True
            
            if progress_bar:
                progress_bar.update(1)
            return False
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                continue
            else:
                if progress_bar:
                    progress_bar.update(1)
                return False
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
                continue
            else:
                if progress_bar:
                    progress_bar.update(1)
                return False
    return False

def main():
    print("正在启动浏览器...")
    # chrome_options = Options()
    # chrome_options.add_argument("--headless") 
    # chrome_options.add_argument("--disable-gpu")
    # chrome_options.add_argument(f"user-agent={headers['User-Agent']}")
    edge_options = EdgeOptions()
    # edge_options.add_argument("--headless") 
    edge_options.add_argument("--disable-gpu")
    edge_options.add_argument(f"user-agent={headers['User-Agent']}")

    # service = Service(ChromeDriverManager().install())
    # driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        # 尝试使用系统路径中的Edge驱动
        service = EdgeService()
        driver = webdriver.Edge(service=service, options=edge_options)
    except Exception as e:
        print(f"使用默认Edge驱动失败: {e}")
        # 如果默认方式失败，可以指定本地的Edge驱动路径（请根据实际路径修改）
        # 示例路径，需要根据实际安装位置修改
        # edge_driver_path = "msedgedriver.exe"  # 或者完整的路径如 r"C:\path\to\msedgedriver.exe"
        # if os.path.exists(edge_driver_path):
        #     service = EdgeService(edge_driver_path)
        #     driver = webdriver.Edge(service=service, options=edge_options)
        # else:
        print("找不到Edge驱动，请确保已安装Microsoft Edge浏览器和对应的驱动程序")
        return
    
    all_image_links = []
    offset = 0
    
    try:
        while True:
            print(f"\n正在处理页面，偏移量: {offset}...")
            url = f"{base_url}&offset={offset}"
            html = fetch_html(url, driver)
            
            if not html:
                print("无法获取HTML，终止抓取。")
                break
                
            image_links = parse_image_links(html)
            if not image_links:
                print("当前页面未找到新的图片链接，抓取完成。")
                break
            
            all_image_links.extend(image_links)
            print(f"找到 {len(image_links)} 个新链接，总计 {len(all_image_links)} 个。")
            offset += 500
            time.sleep(2) # 等待一下，避免过快请求
            
    finally:
        driver.quit()
        print("浏览器已关闭。")

    if not all_image_links:
        print("未能获取到任何图片链接，程序退出。")
        return

    output_dir = "Arknights_PRTS"
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)
    os.chdir(output_dir)
    
    print(f"\n开始下载 {len(all_image_links)} 张图片到 {output_dir} 文件夹...")
    
    failure_count = 0
    max_failures = 10  # 增加最大失败次数阈值
    
    # 使用 tqdm 创建进度条
    with tqdm(total=len(all_image_links), desc="下载进度", ncols=100) as progress_bar:
        with ThreadPoolExecutor(max_workers=5) as executor:  # 减少并发线程数以减轻服务器压力
            future_to_url = {executor.submit(download_image, link, headers, progress_bar): link for link in all_image_links}
            for future in concurrent.futures.as_completed(future_to_url):
                try:
                    success = future.result()
                    if not success:
                        failure_count += 1
                        if failure_count % 5 == 0:  # 每5次失败输出一次提示
                            print(f"\n警告: 已累计 {failure_count} 次下载失败")
                    else:
                        failure_count = 0  # 重置失败计数
                except Exception as exc:
                    failure_count += 1
                    if failure_count % 5 == 0:
                        print(f"\n警告: 已累计 {failure_count} 次下载失败")

                if failure_count >= max_failures:
                    print(f"\n连续失败达到 {max_failures} 次，正在终止所有下载任务...")
                    for f in future_to_url:
                        f.cancel()
                    break

    if failure_count >= max_failures:
        print("程序因失败次数过多而终止。")
    else:
        print("\n所有图片下载任务已处理完毕。")

if __name__ == "__main__":
    main()