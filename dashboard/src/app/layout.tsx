import type { Metadata, Viewport } from "next";
import { Google_Sans_Code, Google_Sans_Flex } from "next/font/google";
import { Providers } from "@/components/providers";
import { ICON_FONT_HREF } from "@/lib/icons";
import "./globals.css";

const sans = Google_Sans_Flex({
  variable: "--font-google-sans-flex",
  subsets: ["latin"],
  axes: ["ROND", "opsz", "wdth", "GRAD"],
  // Next has no metric overrides for this family yet, so declare the fallback
  adjustFontFallback: false,
  fallback: ["Roboto Flex", "system-ui", "sans-serif"],
});

const mono = Google_Sans_Code({
  variable: "--font-google-sans-code",
  subsets: ["latin"],
  adjustFontFallback: false,
  fallback: ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
});

export const metadata: Metadata = {
  title: "FraudGuard",
  description: "Real-time fraud review console",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf8ff" },
    { media: "(prefers-color-scheme: dark)", color: "#090e1b" },
  ],
};

// Before first paint: resolve light/dark (stored choice, else OS) and re-apply
// a user-picked dynamic color scheme so neither flashes the defaults.
const prePaint = `try{var d=document.documentElement,t=localStorage.getItem("fg.theme");if(t!=="light"&&t!=="dark"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}d.dataset.theme=t;var c=localStorage.getItem("fg.schemeCss.v3");if(c){var s=document.createElement("style");s.id="m3-dynamic";s.textContent=c;document.head.appendChild(s)}}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-theme="light"
      suppressHydrationWarning
      className={`${sans.variable} ${mono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: prePaint }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* Icon font: next/font has no Material Symbols, so it loads from Google Fonts */}
        <link rel="stylesheet" href={ICON_FONT_HREF} />
      </head>
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
