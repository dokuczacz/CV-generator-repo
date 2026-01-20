import "./globals.css";

export const metadata = {
  title: "CV Generator",
  description: "Professional CV Generator with ATS compliance and photo extraction",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
