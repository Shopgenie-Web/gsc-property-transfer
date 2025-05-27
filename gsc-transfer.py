import argparse
import time
import subprocess
import json
import csv
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

class GSCVerifier:
    def __init__(self, driver, url):
        self.driver = driver
        self.wait = WebDriverWait(driver, 15)
        self.site_url = url
        self.meta_tag = None
        self.site_id = None
        self.result = "❌ Verification Failed"

    def access_gsc_page(self):
        gsc_url = f"https://search.google.com/u/1/search-console/settings?resource_id={self.site_url}"
        print(f"[INFO] Navigating to {gsc_url}")
        self.driver.get(gsc_url)
        time.sleep(1)

        try:
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//span[@role='heading' and text()='Settings']")))
            print("✅ Property already accessible. No verification needed.")
            self.result = "✅ Already Verified"
            return False
        except:
            pass

        try:
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), \"Oops, you don't have access to this property\")]")))
            print("[INFO] Access denied. Proceeding with manual verification...")
            return True
        except:
            print("⚠️ No access or indicator found. Skipping.")
            return False

    def copy_meta_tag(self):
        try:
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='Verify your ownership']"))).click()
            time.sleep(1)
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='button'][.//span[text()=\"Add a meta tag to your site's home page\"]]"))).click()
            time.sleep(1)
            self.wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='button' and @data-verification-method='2'][.//span[text()='Copy']]"))).click()
            result = subprocess.run(['pbpaste'], stdout=subprocess.PIPE, check=True)
            self.meta_tag = result.stdout.decode('utf-8').strip()
            print("[SUCCESS] Meta tag copied from clipboard.")
        except Exception as e:
            print(f"[ERROR] Could not retrieve meta tag: {e}")
            raise

    def access_duda(self):
        print("[INFO] Accessing Duda dashboard...")
        self.driver.execute_script("window.open('');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        self.driver.get("https://my.duda.co/home/dashboard/sites")
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Search sites']")))
        search_input = self.driver.find_element(By.XPATH, "//input[@placeholder='Search sites']")
        search_input.clear()
        search_input.send_keys(self.site_url)
        time.sleep(2)
        site_link = self.wait.until(EC.presence_of_element_located((By.XPATH, "//a[@data-auto='sites-cell-image']")))
        self.site_id = site_link.get_attribute("href").split("/site/")[1].split("/")[0]
        print(f"[SUCCESS] Site ID extracted: {self.site_id}")

    def inject_meta_tag(self):
        self.driver.get(f"https://my.duda.co/home/site/{self.site_id}/#settings:header")
        time.sleep(4)
        print("[INFO] Injecting meta tag into Head HTML...")
        sanitized_tag = json.dumps("\n" + self.meta_tag)
        script = f'''
        try {{
            var editors = document.querySelectorAll(".ace_editor");
            var targetEditor = null;
            editors.forEach(function(editorEl) {{
                var parent = editorEl.closest("[data-auto='settingswrapperinner']");
                if (parent && parent.textContent.includes("Head HTML")) {{
                    targetEditor = editorEl;
                }}
            }});
            if (targetEditor) {{
                var editor = ace.edit(targetEditor);
                var current = editor.getValue();
                var meta = {sanitized_tag};
                if (!current.includes(meta.trim())) {{
                    editor.setValue(current + meta, -1);
                }}
            }}
        }} catch (err) {{ console.error(err); }}
        '''
        self.driver.execute_script(script)
        time.sleep(1)

    def save_and_publish(self):
        print("[INFO] Clicking Save for Head HTML...")
        header_section = self.wait.until(EC.presence_of_element_located((By.XPATH, "//span[text()='Head HTML']/ancestor::div[@data-auto='settingswrapperinner']")))
        head_save_button = header_section.find_element(By.XPATH, ".//button[@data-auto='save']")
        head_save_button.click()
        time.sleep(1)

        try:
            confirm_button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@data-auto='yes-button']"))
            )
            confirm_button.click()
            print("✅ Confirmed performance warning popup.")
        except TimeoutException:
            print("⚠️ No performance popup.")

        print("[INFO] Republishing site...")
        republish_button = self.wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@data-auto='topBarPublish']")))
        republish_button.click()
        time.sleep(7)
        print("✅ Site republished.")
        self.driver.close()
        self.driver.switch_to.window(self.driver.window_handles[0])

    def verify_gsc(self):
        print("[INFO] Switching back to GSC tab...")
        self.driver.get(f"https://search.google.com/u/1/search-console/settings?resource_id={self.site_url}")
        time.sleep(1)
        self.driver.refresh()
        time.sleep(1)

        try:
            self.driver.find_element(By.XPATH, "//*[text()='Verify your ownership']").click()
            time.sleep(1)
            time.sleep(6)
            self.driver.find_element(By.XPATH, "//*[contains(text(),'Ownership auto verified')]")
            print("✅ Ownership auto verified.")
            self.result = "✅ Verified via HTML Meta Tag"
        except:
            print("❌ Verification may have failed. 'Ownership auto verified' not found.")
            self.result = "❌ Verification Failed"

    def run(self):
        if not self.access_gsc_page():
            return self.result
        try:
            self.copy_meta_tag()
            self.access_duda()
            self.inject_meta_tag()
            self.save_and_publish()
            self.verify_gsc()
        except Exception as e:
            print(f"[ERROR] Process failed: {e}")
        return self.result

def main():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "localhost:9222")
    driver = webdriver.Chrome(options=options)

    results = []
    if not os.path.exists("urls.txt"):
        print("❌ File 'urls.txt' not found.")
        return

    with open("urls.txt", "r") as file:
        urls = [line.strip() for line in file if line.strip()]

    for url in urls:
        print("\n===============================")
        print(f"🔍 Processing: {url}")
        verifier = GSCVerifier(driver, url)
        result = verifier.run()
        results.append({"URL": url, "Result": result})

    driver.quit()

    # Save results to CSV
    with open("verification_results.csv", "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["URL", "Result"])
        writer.writeheader()
        writer.writerows(results)

    print("\n✅ All done! Results saved to 'verification_results.csv'.")

if __name__ == "__main__":
    main()
