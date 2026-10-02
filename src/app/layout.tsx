import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "resipsc v2.0 — Residual PSC Detection for Cell Therapy QC",
  description:
    "Machine-learning ensemble for detecting residual pluripotent stem cells in single-cell RNA-seq of cell therapy products. Research Use Only — NOT FDA-cleared.",
  keywords: [
    "residual PSC",
    "teratoma",
    "cell therapy QC",
    "single-cell RNA-seq",
    "machine learning",
    "21 CFR Part 11",
    "ICH Q5E",
  ],
  authors: [{ name: "resipsc working group" }],
  icons: {
    icon: "https://z-cdn.chatglm.cn/z-ai/static/logo.svg",
  },
  openGraph: {
    title: "resipsc v2.0",
    description: "Residual pluripotent stem cell detection for cell therapy QC",
    siteName: "resipsc",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        {children}
        <Toaster />
      </body>
    </html>
  );
}
