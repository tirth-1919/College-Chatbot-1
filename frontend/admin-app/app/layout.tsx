import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI FAQ College Chat Bot",
  description: "Your college questions answered instantly — admissions, courses, fees, faculty and more.",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: "/icon-192.png",
  },
  openGraph: {
    title: "AI FAQ College Chat Bot",
    description: "Ask anything about your college — instant verified answers.",
    images: ["/ai-faq-logo.png"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
