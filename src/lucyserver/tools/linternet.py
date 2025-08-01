from .lucy_module import LucyModule, available_for_lucy

import requests
import json
import re

from bs4 import BeautifulSoup

BASE = "https://api.search.brave.com/res/v1/web/search"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15"

class LInternet(LucyModule):
    def __init__(self):
        super().__init__("internet")

    def setup(self):
        self.API_KEY = self.load_data("brave_api_key", {"api_key": ""})["api_key"]

    @available_for_lucy
    async def search(self, query):
        """Searches the internet for the given query and returns a list of URL results."""
        
        if self.API_KEY == "":
            return "Brave API key is not set. Ask the user to set it by modifying the configuration file."
        
        out = []
        url = f"{BASE}?q={query}&count=5&result_filter=web"
        headers = {
            "X-Subscription-Token": self.API_KEY,
        }
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return f"Error: {response.status_code} - {response.text}"
        results = response.json()["web"]["results"]
        for result in results:
            out.append({
                "title": result["title"],
                "url": result["url"],
            })
        return out

    @available_for_lucy
    async def view_page(self, url, question=None):
        """Gets a natrual language answer to the specified question from the given URL. If the question is none, a summary of the page is returned."""
        headers = {
            "User-Agent": USER_AGENT
        }
        site_data = requests.get(url, headers=headers)
        if site_data.status_code != 200:
            # return f"Error: {site_data.status_code} - {site_data.text}"
            return {"error": f"Failed to fetch page: {site_data.status_code}"}
        site_content = site_data.text

        site_content = BeautifulSoup(site_content, "html.parser")

        for tag in site_content(['script', 'style', 'footer', 'nav', 'aside', 'header']):
            tag.decompose()

        main_content = site_content.find("main")
        if main_content:
            site_content = main_content
        
        site_content = site_content.get_text(separator="\n", strip=True)
        # write out the content to a file for debugging
        with open(f"{url.replace('https://', '').replace('http://', '').replace('/', '_')}.txt", "w") as f:
            f.write(site_content)


        if question is None:
            question = f"Summarize the content of this page"
            

        # if the page has a main tag, use that as the content


        prompt = f"# Page Contents\n{site_content}\n\n# Question\n{question}\n\n"
        completion = self.session.get_openai_client().chat.completions.create(
            model=self.session.MODEL_NAME,
            messages=[
                {"role": "system", "content": "You extract answers to questions from web pages. Do not reply in complete sentences, instead just return the answer and a quote from the page."},
                {"role": "user", "content": prompt}
            ]
        )
        output = completion.choices[0].message.content
        return {"extracted_answer": output, "source": url, "note": "Remember to reiterate the answer for the user."}


if __name__ == "__main__":
    import asyncio

    internet_tool = LInternet()
    # print(asyncio.run(internet_tool.search("raspberry pi 5 power draw")))