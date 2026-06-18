<?php

namespace App\Services;

use InvalidArgumentException;
use PhpOffice\PhpSpreadsheet\IOFactory;
use PhpOffice\PhpSpreadsheet\Spreadsheet;
use PhpOffice\PhpSpreadsheet\Style\Alignment;
use PhpOffice\PhpSpreadsheet\Style\Fill;
use Throwable;

/**
 * EXCEL BULK IMPORT — generate the sample template, and parse uploads.
 * A line-for-line port of the Python excel_service; same design:
 *
 * - Validation is PER ROW and never trusts the file. A spreadsheet is
 *   just untrusted input wearing a friendly extension. We collect the
 *   good rows and a per-row reason for every bad one, so the user
 *   fixes 3 rows instead of being told "invalid file".
 *
 * - The parser returns plain arrays; the CONTROLLER decides what to
 *   insert. Keeping DB writes out of here keeps this testable.
 */
class ExcelService
{
    /** The contract between the sample file and the parser. */
    public const COLUMNS = ['keyword', 'current_rank', 'previous_rank'];

    public const MAX_ROWS = 1000; // guard against a 1M-row monster

    public static function buildSampleSpreadsheet(): Spreadsheet
    {
        $spreadsheet = new Spreadsheet();
        $sheet = $spreadsheet->getActiveSheet();
        $sheet->setTitle('Keywords');

        // Header row
        $sheet->fromArray(['Keyword', 'Current Rank', 'Previous Rank (optional)'], null, 'A1');
        $sheet->getStyle('A1:C1')->applyFromArray([
            'font' => ['bold' => true, 'name' => 'Arial', 'color' => ['rgb' => 'FFFFFF']],
            'fill' => ['fillType' => Fill::FILL_SOLID, 'startColor' => ['rgb' => 'EA580C']], // the app's orange
            'alignment' => [
                'horizontal' => Alignment::HORIZONTAL_LEFT,
                'vertical' => Alignment::VERTICAL_CENTER,
            ],
        ]);
        $sheet->getRowDimension(1)->setRowHeight(22);

        // Example rows (clearly illustrative)
        $examples = [
            ['online yoga classes', 4, 9],
            ['meditation retreat rishikesh', 12, 8],
            ['pranayama breathing course', 3, null], // blank previous = "New"
        ];
        $sheet->fromArray($examples, null, 'A2');
        $sheet->getStyle('A2:C'.(1 + count($examples)))->applyFromArray([
            'font' => ['name' => 'Arial'],
        ]);

        $sheet->getColumnDimension('A')->setWidth(38);
        $sheet->getColumnDimension('B')->setWidth(16);
        $sheet->getColumnDimension('C')->setWidth(24);

        // Notes a couple of rows below the data
        $notesStart = 2 + count($examples) + 1;
        $notes = [
            'How to use this template:',
            '• Replace the example rows above with your own keywords.',
            '• Keyword: the search term (required).',
            '• Current Rank: a whole number, 1 or higher (required).',
            '• Previous Rank: a whole number, 1 or higher — leave blank for a brand-new keyword.',
            '• Keep the header row. Delete these notes if you like.',
            '• Up to '.self::MAX_ROWS.' keywords per file.',
        ];
        foreach ($notes as $i => $line) {
            $row = $notesStart + $i;
            $sheet->setCellValue('A'.$row, $line);
            $sheet->getStyle('A'.$row)->applyFromArray([
                'font' => [
                    'name' => 'Arial',
                    'italic' => true,
                    'bold' => $i === 0,
                    'color' => ['rgb' => '78716C'],
                ],
            ]);
        }

        return $spreadsheet;
    }

    /**
     * Parse an uploaded .xlsx from a file path.
     *
     * @return array{0: list<array{term: string, currentRank: int, previousRank: int|null}>,
     *               1: list<array{row: int, reason: string}>}  [valid, errors]
     */
    public static function parseKeywordWorkbook(string $path): array
    {
        try {
            $spreadsheet = IOFactory::load($path);
        } catch (Throwable $e) {
            throw new InvalidArgumentException("That file couldn't be read as an Excel (.xlsx) workbook.");
        }

        $sheet = $spreadsheet->getActiveSheet();
        // nullValue=null, calculate formulas, no display formatting,
        // numeric (0-based) column keys.
        $rows = $sheet->toArray(null, true, false, false);

        $valid = [];
        $errors = [];
        $seenTerms = [];
        $dataRows = 0;

        foreach ($rows as $idx => $row) {
            $excelRow = $idx + 1;
            if ($excelRow === 1) {
                continue; // header
            }

            $termRaw = $row[0] ?? null;
            $curRaw = $row[1] ?? null;
            $prevRaw = $row[2] ?? null;

            // Fully blank row -> silently skip (trailing empties, etc.)
            $termBlank = $termRaw === null || (is_string($termRaw) && trim($termRaw) === '');
            if ($termBlank && $curRaw === null && $prevRaw === null) {
                continue;
            }

            // Skip the template's own notes block if left in.
            if (is_string($termRaw)) {
                $trimmed = trim($termRaw);
                if (str_starts_with($trimmed, 'How to use') || str_starts_with($trimmed, '•')) {
                    continue;
                }
            }

            $dataRows++;
            if ($dataRows > self::MAX_ROWS) {
                $errors[] = ['row' => $excelRow, 'reason' => 'File exceeds the '.self::MAX_ROWS.'-keyword limit; remaining rows ignored.'];
                break;
            }

            $term = $termRaw === null ? '' : strtolower(trim((string) $termRaw));
            if ($term === '') {
                $errors[] = ['row' => $excelRow, 'reason' => 'Missing keyword.'];
                continue;
            }

            $cur = self::cleanInt($curRaw);
            if ($cur === null) {
                $errors[] = ['row' => $excelRow, 'reason' => 'Missing current rank.'];
                continue;
            }
            if ($cur === false || $cur < 1) {
                $errors[] = ['row' => $excelRow, 'reason' => 'Current rank must be a whole number of 1 or more (got '.self::repr($curRaw).').'];
                continue;
            }

            $prev = self::cleanInt($prevRaw);
            if ($prev === false || (is_int($prev) && $prev < 1)) {
                $errors[] = ['row' => $excelRow, 'reason' => 'Previous rank must be blank or a whole number of 1 or more (got '.self::repr($prevRaw).').'];
                continue;
            }
            // $prev is null (blank) or a valid int here.

            // Duplicate within the same file -> keep the first, flag the rest.
            if (isset($seenTerms[$term])) {
                $errors[] = ['row' => $excelRow, 'reason' => 'Duplicate of an earlier row for “'.$term.'”; skipped.'];
                continue;
            }
            $seenTerms[$term] = true;

            $valid[] = ['term' => $term, 'currentRank' => $cur, 'previousRank' => $prev];
        }

        return [$valid, $errors];
    }

    /**
     * Accept 5, 5.0, "5", " 5 " -> 5. Blank -> null. Junk -> false.
     * Mirrors the Python _clean_int, including its quirks.
     */
    private static function cleanInt(mixed $value): int|false|null
    {
        if ($value === null || (is_string($value) && trim($value) === '')) {
            return null; // blank
        }
        if (is_int($value)) {
            return $value;
        }
        if (is_float($value)) {
            // floats that aren't whole numbers (5.5) are invalid ranks
            return floor($value) == $value ? (int) $value : false;
        }
        if (is_string($value)) {
            $head = explode('.', trim($value))[0];
            if ($head !== '' && ctype_digit($head)) {
                return (int) $head;
            }
        }

        return false; // present but unparseable
    }

    /** Python-style repr for error messages ('abc' stays quoted, 5.5 doesn't). */
    private static function repr(mixed $v): string
    {
        if (is_string($v)) {
            return "'".$v."'";
        }
        if ($v === null) {
            return 'None';
        }
        if (is_bool($v)) {
            return $v ? 'True' : 'False';
        }

        return (string) $v;
    }
}
