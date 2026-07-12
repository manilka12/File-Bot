# Document Scanner Bot

A WhatsApp-based bot that enables users to perform various document operations directly through a chat interface.

## Features

- **PDF Manipulation:** Merge, split, and compress PDF files.
- **Document Scanning:** Convert images into formatted scanned PDFs.
- **Format Conversion:** Convert Word (`.docx`), PowerPoint (`.pptx`), and Excel (`.xlsx`) files to PDF.
- **Markdown to PDF:** Convert Markdown text into formatted PDF documents, featuring a multi-level fallback system (`md-to-pdf` -> `md2pdf` -> `pandoc`) to ensure reliable generation.

## Requirements

- Python 3.8+ (or compatible version)
- WhatsApp API integration credentials

## Setup and Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/manilka12/File-Bot.git
   cd File-Bot
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirement.txt
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit the `.env` file with your specific configuration:
   - `BASE_URL`: The base URL for the WhatsApp API (default: `http://localhost:8081`)
   - `API_TOKEN`: Your WhatsApp API token
   - `INSTANCE_ID`: The WhatsApp instance ID (default: `whatsapp`)
   - `INSTANCE_TOKEN`: Your WhatsApp instance token
   - `LOG_LEVEL`: Logging level (default: `INFO`)

4. Run the application:
   ```bash
   python app/main.py
   ```

## Usage

Interact with the bot by sending the following text commands through WhatsApp:

| Command | Action |
| :--- | :--- |
| `merge pdf` | Start a PDF merge workflow |
| `split pdf` | Start a PDF split workflow |
| `scan document` | Start a document scanning workflow |
| `word to pdf` | Convert Word documents to PDF |
| `powerpoint to pdf` | Convert PowerPoint presentations to PDF |
| `excel to pdf` | Convert Excel spreadsheets to PDF |
| `compress pdf` | Start a PDF compression workflow |
| `markdown to pdf` | Convert Markdown text to PDF |

## License

This project is licensed under the [MIT License](LICENSE).
