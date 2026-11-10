# ReceivAI UAE frontend setup

This frontend uses Next.js 16 App Router, React 19 and Bootstrap 5. It does not use Tailwind CSS.

## 1. Install dependencies

```powershell
cd frontend
npm install
```

## 2. Configure the API address

Create `frontend/.env.local` with:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

Do not put database credentials, OpenAI keys, or other backend secrets in this file.

## 3. Start the application

Start the FastAPI backend in its own terminal first, then:

```powershell
npm run dev
```

Open http://localhost:3000.

## 4. Sign in

Use the administrator account configured in the backend. The frontend stores the returned short-lived access token in browser local storage for this development MVP.

## 5. Test invoice uploads

Open Invoice Management and choose a PDF, DOCX, XLSX, XLS or CSV file (maximum 10 MB). Select **Upload and extract**, inspect the extraction preview, then review any invoice details. Uploading never approves an invoice; select **Approve and save invoice** only after administrator review.

## Notes

- The dashboard loads invoice, payment reminder and summary data from the FastAPI API.
- PyMuPDF, python-docx, pandas, openpyxl and xlrd extract the supported formats. PDF and DOCX text can be sent to the configured OpenAI agent for field extraction; spreadsheet contents remain available for administrator review and are not sent to OpenAI. OCR fallback requires a working Tesseract installation; if OCR is unavailable, the preview reports a warning.
- Forecasting and AI chat screens are visual placeholders until their backend agents are implemented; they do not display fabricated results.
- For production, use secure, HttpOnly cookie-based authentication and private persistent object storage rather than browser local storage and local disk storage.
