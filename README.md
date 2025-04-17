# Document Scanner Bot

A WhatsApp-based document processing bot that enables users to perform various document operations through a chat interface.

## Features

<<<<<<< HEAD
- **PDF Manipulation**: Merge, split, and compress PDF files
- **Document Scanning**: Convert images into scanned document PDFs
- **Format Conversion**: Convert Word, PowerPoint, Excel files to PDF
- **Markdown to PDF**: Convert markdown text to PDF documents
=======
- **PDF Merging**: Combine multiple PDF documents into a single file
- **PDF Splitting**: Extract specific pages or page ranges from a PDF
- **Document Scanning**: Convert images into professional-looking scanned documents
- **File Format Conversion**:
  - Word to PDF
  - PowerPoint to PDF
  - Excel to PDF
- **PDF Compression**: Reduce PDF file size with adjustable compression levels
- **Markdown to PDF**: Convert markdown text into formatted PDF documents

## Markdown to PDF Conversion

The system provides a robust Markdown-to-PDF conversion with automatic fallback mechanisms:

1. First attempts conversion using `md-to-pdf` (ARM-compatible)
2. Falls back to `md2pdf` if the first method fails
3. Falls back to `pandoc` as a last resort
>>>>>>> 0789c32 (Refactor markdown to PDF functionality with fallback mechanisms)

## Requirements

See `requirement.txt` for a list of dependencies.

## Setup and Installation

1. Clone this repository
<<<<<<< HEAD
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
=======
2. Install dependencies: `pip install -r requirement.txt`
3. Configure WhatsApp connection settings in `config/settings.py`
4. Run the application: `python app/main.py`
>>>>>>> 0789c32 (Refactor markdown to PDF functionality with fallback mechanisms)

## Usage

Send the following commands to the bot through WhatsApp:

- `merge pdf` - Start a PDF merge workflow
- `split pdf` - Start a PDF split workflow
- `scan document` - Start a document scanning workflow
- `word to pdf` - Convert Word documents to PDF
- `powerpoint to pdf` - Convert PowerPoint presentations to PDF
- `excel to pdf` - Convert Excel spreadsheets to PDF
- `compress pdf` - Start a PDF compression workflow
- `markdown to pdf` - Convert markdown text to PDF

## License

<<<<<<< HEAD
[MIT License](LICENSE)
=======
See the LICENSE file for details.
>>>>>>> 0789c32 (Refactor markdown to PDF functionality with fallback mechanisms)
