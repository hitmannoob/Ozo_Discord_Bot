# 🤖 Ozo: The Smart Academic Resource Bot

**Ozo transforms your academic and professional Discord server into a personalized knowledge-sharing hub.**

Leveraging **OpenAI's LLMs** and **profile matching**, Ozo intelligently scans shared links and documents, automatically tagging users whose registered skills and interests are relevant to the content. Never miss a critical resource in a busy chat again!

---

## ✨ Features

Based on the code, Ozo offers powerful functionality:

* **Intelligent Resource Detection:** Automatically scans all messages for **URLs** and **document attachments** (`.pdf`, `.docx`, `.doc`, `.txt`, `.md`).
* **AI-Powered Content Analysis:** Uses a powerful LLM (**GPT-5-Mini**) to analyze web content (via **BeautifulSoup**) and document text (via **PyPDF2/docx**) to extract relevant technical keywords.
* **Personalized Tagging:** Compares extracted keywords against user profiles and sends a mention only to relevant users.
* **Profile Management (`/register`, `/profile`):** Users can easily register and update their Job Title, Skills, and Interests via a Discord **Modal**.
* **Server Theme Configuration (`/set_theme`):** Admins can define the overall server topic (e.g., "AI Research") to provide context for the LLM analysis.
* **SQLite Database:** Persistent storage for user profiles and server configurations using `sqlite3`.

---

## 🛠️ Technology Stack

| Component | Library/Tool | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.9+ | Core application logic. |
| **Bot Framework** | `discord.py` (`commands.Bot`) | Handling Discord events and slash commands. |
| **AI Integration** | `openai` (`AsyncOpenAI`) | Analyzing resource content and extracting keywords. |
| **Web Scraping** | `aiohttp`, `BeautifulSoup4` | Fetching and parsing HTML content from URLs. |
| **Document Parsing** | `PyPDF2`, `python-docx` | Extracting text from PDF and Word documents. |
| **Data Storage** | `sqlite3` (built-in) | Persistent storage for user profiles (`users`) and server settings (`server_configs`). |
| **Configuration**| `os` | Environment variable management. |

### `requirements.txt` (Confirmed Dependencies)

```bash
discord
openai
pydantic
PyPDF2
python-docx
aiohttp
beautifulsoup4
