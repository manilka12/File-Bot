# Document Scanner

A WhatsApp bot for document scanning, PDF manipulation, and format conversion.

## Features

- **PDF Manipulation**: Merge, split, and compress PDF files
- **Document Scanning**: Convert images into scanned document PDFs
- **Format Conversion**: Convert Word, PowerPoint, Excel files to PDF
- **Markdown to PDF**: Convert markdown text to PDF documents
- **PDF to Markdown**: Convert PDF documents to markdown text using vb64/markdown-pdf

## Requirements

See `requirements.txt` for the complete list of dependencies.

## Installation

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Install additional dependencies:
   ```
   pip install git+https://github.com/vb64/markdown-pdf.git
   ```

## Usage

1. Configure your WhatsApp client settings in `config/settings.py`
2. Run the application:
   ```
   python app/main.py
   ```

## Workflows

- **merge**: Merge multiple PDFs into one
- **split**: Split a PDF into multiple parts
- **scan**: Convert images to scanned document PDFs
- **word_to_pdf**: Convert Word documents to PDF
- **powerpoint_to_pdf**: Convert PowerPoint presentations to PDF
- **excel_to_pdf**: Convert Excel spreadsheets to PDF
- **compress**: Compress PDF files
- **markdown_to_pdf**: Convert markdown text to PDF
- **markdown2_to_pdf**: Convert PDF to markdown text

## License

[MIT License](LICENSE)