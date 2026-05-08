import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Realm",
  description: "Solo economic civilization prototype",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
