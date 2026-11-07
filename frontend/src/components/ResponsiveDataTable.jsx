import { Children, cloneElement, isValidElement } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";

function getText(node) {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);

  return Children.toArray(node)
    .map((child) => (isValidElement(child) ? getText(child.props.children) : getText(child)))
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

function getColumnLabels(table) {
  const tableHead = Children.toArray(table.props.children).find(
    (child) => isValidElement(child) && child.type === TableHead,
  );
  const headerRow = tableHead && Children.toArray(tableHead.props.children).find(
    (child) => isValidElement(child) && child.type === TableRow,
  );

  if (!headerRow) return [];

  return Children.toArray(headerRow.props.children)
    .filter((cell) => isValidElement(cell) && cell.type === TableCell)
    .map((cell) => getText(cell.props.children) || cell.props["aria-label"] || "");
}

function addMobileLabels(table, labels) {
  const sections = Children.map(table.props.children, (section) => {
    if (!isValidElement(section) || section.type !== TableBody) return section;

    const rows = Children.map(section.props.children, (row) => {
      if (!isValidElement(row) || row.type !== TableRow) return row;

      const cells = Children.map(row.props.children, (cell, index) => {
        if (
          !isValidElement(cell)
          || cell.type !== TableCell
          || Number(cell.props.colSpan || 1) > 1
          || cell.props["data-label"]
        ) {
          return cell;
        }

        return cloneElement(cell, { "data-label": labels[index] || "" });
      });

      return cloneElement(row, { children: cells });
    });

    return cloneElement(section, { children: rows });
  });

  return cloneElement(table, { children: sections });
}

export default function ResponsiveDataTable({ children, className = "", ...props }) {
  const table = Children.toArray(children).find(
    (child) => isValidElement(child) && child.type === Table,
  );
  const labels = table ? getColumnLabels(table) : [];
  const enhancedChildren = Children.map(children, (child) => (
    isValidElement(child) && child.type === Table
      ? addMobileLabels(child, labels)
      : child
  ));

  return (
    <TableContainer
      {...props}
      className={`${className} responsive-data-table`.trim()}
    >
      {enhancedChildren}
    </TableContainer>
  );
}
