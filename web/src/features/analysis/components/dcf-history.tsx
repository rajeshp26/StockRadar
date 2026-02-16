import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
  } from "@/components/ui/table";
  import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
  import { useDcfHistory } from "../hooks/useDcfHistory";
  
  export function DcfHistory({ symbol }: { symbol: string }) {
    const { items, loading, error } = useDcfHistory(symbol);
  
    if (loading) return null;
  
    return (
      <Card>
        <CardHeader>
          <CardTitle>DCF History</CardTitle>
        </CardHeader>
  
        <CardContent>
          {error && (
            <div className="text-sm text-red-500 mb-2">
              Failed to load DCF history
            </div>
          )}
  
          {!items || items.length === 0 ? (
            <div className="text-sm text-slate-500">
              No prior DCF valuation runs available.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Intrinsic / Share</TableHead>
                  <TableHead>WACC</TableHead>
                  <TableHead>Terminal Method</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Category</TableHead>
                </TableRow>
              </TableHeader>
  
              <TableBody>
                {items.map((h, idx) => (
                  <TableRow key={idx}>
                    <TableCell>
                      {h.runAt
                        ? new Date(h.runAt).toLocaleDateString()
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {h.intrinsicValuePerShare != null
                        ? h.intrinsicValuePerShare.toFixed(2)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {h.waccUsed != null
                        ? `${(h.waccUsed * 100).toFixed(2)}%`
                        : "—"}
                    </TableCell>
                    <TableCell>{h.terminalMethod ?? "—"}</TableCell>
                    <TableCell>{h.score ?? "—"}</TableCell>
                    <TableCell>{h.category ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    );
  }