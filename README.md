# Document Scanner

A WhatsApp bot for document scanning, PDF manipulation, and format conversion.

## Features

- **PDF Manipulation**: Merge, split, and compress PDF files
- **Document Scanning**: Convert images into scanned document PDFs
- **Format Conversion**: Convert Word, PowerPoint, Excel files to PDF
- **Markdown to PDF**: Convert markdown text to PDF documents

## Requirements

See `requirements.txt` for the complete list of dependencies.

## Installation

1. Clone this repository
2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set up environment variables:
   ```
   cp .env.example .env
   ```
   Then edit the `.env` file with your specific configuration.

## Configuration

The application uses environment variables for configuration. You can set these in a `.env` file in the root directory:

- `BASE_URL`: The base URL for the WhatsApp API (default: http://localhost:8081)
- `API_TOKEN`: Your WhatsApp API token
- `INSTANCE_ID`: The WhatsApp instance ID (default: whatsapp)
- `INSTANCE_TOKEN`: Your WhatsApp instance token
- `LOG_LEVEL`: Logging level (default: INFO)

## Usage

1. Configure your environment variables in the `.env` file
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
