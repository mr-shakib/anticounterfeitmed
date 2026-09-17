import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MedSecure PQC — Staff",
  description: "Manufacturer and platform administration.",
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
