/**
 * The price history island of a project page (SPEC 11a §8).
 *
 * It gets only the slug and asks GET /projects/{slug} from the browser when it comes into view:
 * the history never goes into the static site, so the API's per-client limit protects it. The
 * query never retries a 429 or a 404 and never refetches on focus, because every request counts
 * against the reader's daily limit.
 */
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { Button } from "@/components/ui/button";
import { type ChartConfig, ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { browserApiClient, type ProjectDetailOut } from "@/lib/api/client";
import {
  formatCop,
  formatDate,
  formatDateShort,
  formatDayMonth,
  formatMillions,
  formatPct,
  formatRetryAt,
} from "@/lib/format";
import {
  dailySeries,
  dayTicks,
  historySummary,
  isolatedDays,
  type PricePoint,
  priceAxis,
  priceChanges,
  timeToDay,
} from "@/lib/history";
import { toProjectView } from "@/lib/projects";

/** A failed request, with what the island needs to explain it. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly retryAfterSeconds: number | null,
  ) {
    super(`GET /projects/{slug} answered ${status}`);
  }
}

async function fetchProject(slug: string, signal: AbortSignal): Promise<ProjectDetailOut> {
  const { data, response } = await browserApiClient().GET("/projects/{slug}", {
    params: { path: { slug } },
    signal,
  });
  if (data) return data;
  const retryAfter = Number(response.headers.get("Retry-After"));
  throw new ApiError(response.status, Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null);
}

/** One retry, only for a server error or a network failure; never for a 429 or a 404. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false;
  return error instanceof ApiError ? error.status >= 500 : true;
}

type Props = { slug: string };

export default function HistoryChart({ slug }: Props) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: Infinity, refetchOnWindowFocus: false, retry: shouldRetry },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <History slug={slug} />
    </QueryClientProvider>
  );
}

const CHART_HEIGHT = "h-80";

function History({ slug }: Props) {
  const query = useQuery({
    queryKey: ["project", slug],
    queryFn: ({ signal }) => fetchProject(slug, signal),
  });

  if (query.isPending) {
    // The size of the loaded chart, so nothing jumps when it arrives.
    return (
      <div aria-busy="true" className="flex flex-col gap-6">
        <span className="sr-only">Cargando el histórico de precios…</span>
        <Skeleton className="h-16 w-full max-w-md" />
        <Skeleton className={`${CHART_HEIGHT} w-full`} />
        <Skeleton className="h-6 w-2/3" />
      </div>
    );
  }

  if (query.isError) {
    const error = query.error;
    if (error instanceof ApiError && error.status === 429) {
      const when = error.retryAfterSeconds ? formatRetryAt(error.retryAfterSeconds) : "más tarde";
      return (
        <Notice>
          Consultaste muchas fichas en poco tiempo. Podrás ver la gráfica {when}.
        </Notice>
      );
    }
    if (error instanceof ApiError && error.status === 404) {
      return <Notice>Este proyecto ya no está en el catálogo, así que no hay histórico que mostrar.</Notice>;
    }
    return (
      <Notice>
        <span>No pudimos cargar el histórico: el servidor no respondió.</span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          Reintentar
        </Button>
      </Notice>
    );
  }

  const project = query.data;
  const view = toProjectView(project);
  // Unit types with prices, in the page's order (current first, by price).
  const order = new Map(view.unitTypes.map((unit, i) => [unit.id, i]));
  const units = project.unit_types
    .filter((unit) => unit.history.length > 0)
    .sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
  const first = units[0];
  if (!first) return <Notice>Este proyecto no tiene precios publicados todavía.</Notice>;
  const selected = view.from?.id ?? first.id;

  return (
    <Tabs defaultValue={selected}>
      {units.length > 1 && (
        <TabsList aria-label="Tipología">
          {units.map((unit) => (
            <TabsTrigger key={unit.id} value={unit.id}>
              {unit.name}
            </TabsTrigger>
          ))}
        </TabsList>
      )}
      {units.map((unit) => (
        <TabsContent key={unit.id} value={unit.id} className="flex flex-col gap-6">
          <UnitHistory
            name={unit.name}
            changePct={unit.change_since_first_pct}
            points={unit.history.map((h) => ({ priceCop: h.price_cop, observedOn: h.observed_on }))}
          />
        </TabsContent>
      ))}
    </Tabs>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <div
      role="status"
      className="flex flex-col items-start gap-4 rounded-md border-(length:--border-width-default) border-border-input bg-bg-subtle p-6 text-body text-text-secondary"
    >
      {children}
    </div>
  );
}

const chartConfig = { price: { label: "Precio", color: "var(--color-action)" } } satisfies ChartConfig;

function UnitHistory({
  name,
  changePct,
  points,
}: {
  name: string;
  changePct: number | null;
  points: PricePoint[];
}) {
  const series = dailySeries(points);
  const changes = priceChanges(points);
  const singleDay = series.length <= 1;
  const isolated = isolatedDays(series);
  const axis = priceAxis(points);

  return (
    <>
      {singleDay ? (
        <p className="text-body text-text-secondary">
          Solo tenemos el precio del {formatDate(points[0]?.observedOn ?? "")}. La gráfica aparece
          cuando cambie.
        </p>
      ) : (
        <>
          {/* The chart is for the eye; the summary and the table say the same in text. */}
          <ChartContainer config={chartConfig} className={`${CHART_HEIGHT} w-full`} aria-hidden="true">
            <LineChart data={series} margin={{ top: 8, right: 16, bottom: 0, left: 0 }} accessibilityLayer={false}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                ticks={dayTicks(series)}
                tickFormatter={(t: number) => formatDayMonth(timeToDay(t))}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <YAxis
                domain={axis.domain}
                ticks={axis.ticks}
                tickFormatter={(value: number) => formatMillions(value)}
                tickLine={false}
                axisLine={false}
                width={112}
              />
              <ChartTooltip cursor content={<PriceTooltip />} isAnimationActive={false} />
              <Line
                dataKey="priceCop"
                type="stepAfter"
                stroke="var(--color-price)"
                strokeWidth={2}
                connectNulls={false}
                isAnimationActive={false}
                dot={(props: { cx?: number; cy?: number; payload?: { day: string }; index?: number }) =>
                  props.payload && isolated.has(props.payload.day) ? (
                    <circle key={props.index} cx={props.cx} cy={props.cy} r={3} fill="var(--color-price)" />
                  ) : (
                    <g key={props.index} />
                  )
                }
                activeDot={{ r: 4, fill: "var(--color-price)" }}
              />
            </LineChart>
          </ChartContainer>
          <p className="text-body-lg text-text-primary">{historySummary(points, changePct)}</p>
        </>
      )}
      <Table label={`Cambios de precio de ${name}`} className="tabular-nums">
        <TableCaption className="sr-only">
          Días en que cambió el precio de {name}, desde el primer precio observado
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Fecha</TableHead>
            <TableHead>Precio</TableHead>
            <TableHead>Cambio</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {changes.map((row) => (
            <TableRow key={row.observedOn}>
              <TableCell>{formatDateShort(row.observedOn)}</TableCell>
              <TableCell className="font-bold text-text-primary">{formatCop(row.priceCop)}</TableCell>
              <TableCell>{row.changePct === null ? "Primer precio" : formatPct(row.changePct)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}

type TooltipProps = {
  active?: boolean;
  payload?: { payload?: { day: string; priceCop: number | null } }[];
};

function PriceTooltip({ active, payload }: TooltipProps) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="flex flex-col gap-1 rounded-md border-(length:--border-width-default) border-border-input bg-bg-surface px-3 py-2 shadow-sm">
      <span className="text-caption text-text-muted">{formatDate(point.day)}</span>
      <span className="text-price text-text-price">
        {point.priceCop === null ? "Sin observación" : formatCop(point.priceCop)}
      </span>
    </div>
  );
}
