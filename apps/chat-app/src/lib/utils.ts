import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
export function generateSchemaMarkdown(schema: any, selectedTables?: string[]): string {
  if (!schema || !schema.tables) return "";

  let md = "### Database Schema\n\n";
  const tables = selectedTables
    ? schema.tables.filter((t: any) => selectedTables.includes(t.table_name))
    : schema.tables;

  tables.forEach((table: any) => {
    md += `#### Table: ${table.table_name}\n`;
    md += `*Description: ${table.description}*\n`;

    // Process columns
    if (table.columns) {
      Object.entries(table.columns).forEach(([colName, colDesc]) => {
        md += `- ${colName}: ${colDesc}\n`;
      });
    }

    // Add negative constraints if found in description
    if (table.description.toUpperCase().includes("DO NOT USE") || table.description.toUpperCase().includes("PROHIBITION")) {
      const notes = table.description.split('.').filter((s: string) =>
        s.toUpperCase().includes("DO NOT USE") || s.toUpperCase().includes("PROHIBITION")
      );
      notes.forEach((note: string) => {
        md += `  - **IMPORTANT: ${note.trim()}.**\n`;
      });
    }

    md += "\n";
  });

  return md;
}
