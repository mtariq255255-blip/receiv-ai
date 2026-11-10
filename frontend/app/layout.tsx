import type { Metadata } from "next";
import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap-icons/font/bootstrap-icons.css";
import "./globals.css";
export const metadata: Metadata = { title: "ReceivAI UAE | Agentic Finance Operations", description: "Invoice intelligence and receivables visibility for UAE SMEs." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
