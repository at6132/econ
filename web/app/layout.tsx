import type { Metadata } from "next";
import "./globals.css";

import { RealmClientRoot } from "./RealmClientRoot";

export const metadata: Metadata = {
  title: "Realm",
  description: "Solo economic civilization prototype",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <RealmClientRoot>{children}</RealmClientRoot>
      </body>
    </html>
  );
}
