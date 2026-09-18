package com.runproof.controlplane;

import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.baggage.Baggage;
import io.opentelemetry.api.baggage.BaggageBuilder;
import io.opentelemetry.api.baggage.propagation.W3CBaggagePropagator;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.common.AttributesBuilder;
import io.opentelemetry.api.metrics.DoubleHistogram;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.metrics.Meter;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanBuilder;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.propagation.TextMapSetter;
import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import io.opentelemetry.sdk.trace.export.SpanExporter;
import io.opentelemetry.sdk.trace.data.SpanData;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.servlet.http.HttpServletRequest;

import java.net.URI;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.regex.Pattern;

/**
 * Optional, diagnostic-only OpenTelemetry boundary for the formal Control
 * Plane.  The service deliberately owns no canonical state and is completely
 * inert until an explicit endpoint is configured and enabled.
 */
@Service
public class ObservabilityService {

    public static final String CONTEXT_SCHEMA = "rpf-otel-context-v1";
    public static final String JOB_ID = "runproof.job.id";
    public static final String ATTEMPT_ID = "runproof.attempt.id";
    public static final String RUN_ID = "runproof.run.id";
    public static final String ENVIRONMENT_ID = "runproof.environment.id";
    public static final String OPERATION_ID = "runproof.operation.id";
    public static final String AGENT_ID = "runproof.agent.id";
    public static final String OUTCOME = "runproof.outcome";
    public static final String FAULT_PROFILE = "runproof.fault.profile";
    public static final String TELEMETRY_COMPLETENESS = "runproof.telemetry.completeness";

    public static final Set<String> BAGGAGE_ALLOWLIST = Set.of(
            JOB_ID, ATTEMPT_ID, RUN_ID, ENVIRONMENT_ID, OPERATION_ID
    );
    public static final Set<String> ATTRIBUTE_ALLOWLIST = Set.of(
            "service.name", "service.version", JOB_ID, ATTEMPT_ID, RUN_ID,
            ENVIRONMENT_ID, OPERATION_ID, AGENT_ID, OUTCOME, FAULT_PROFILE,
            TELEMETRY_COMPLETENESS, "runproof.job.type", "runproof.target.type",
            "runproof.attempt.model", "runproof.previous.attempt", "runproof.new.attempt",
            "runproof.durable.boundary", "runproof.response.lost", "runproof.error.type",
            "runproof.reconcile.status", "runproof.effect.count", "runproof.mutation.count",
            "runproof.propagation.valid", "http.method", "http.route", "http.status_code",
            "db.system", "db.operation.name"
    );
    private static final Pattern SAFE_VALUE = Pattern.compile("[A-Za-z0-9._:-]{1,200}");
    private static final Pattern SAFE_ROUTE = Pattern.compile("/[A-Za-z0-9._:/{}-]{1,200}");
    private static final TextMapSetter<Map<String, String>> MAP_SETTER = (carrier, key, value) -> {
        if (carrier != null && key != null && value != null) carrier.put(key, value);
    };
    private static final TextMapGetter<HttpServletRequest> REQUEST_GETTER = new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(HttpServletRequest carrier) {
            return carrier == null ? List.of() : Collections.list(carrier.getHeaderNames());
        }

        @Override
        public String get(HttpServletRequest carrier, String key) {
            return carrier == null || key == null ? null : carrier.getHeader(key);
        }
    };

    private final Logger logger = LoggerFactory.getLogger(ObservabilityService.class);
    private final boolean configuredEnabled;
    private final String configuredEndpoint;
    private final String serviceName;
    private final int queueSize;
    private final AtomicBoolean initialized = new AtomicBoolean(false);
    private final AtomicLong exportedSpans = new AtomicLong();
    private final AtomicLong exportFailures = new AtomicLong();
    private final AtomicLong droppedSpans = new AtomicLong();
    private final ConcurrentHashMap<String, LongCounter> counters = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, DoubleHistogram> histograms = new ConcurrentHashMap<>();

    private volatile OpenTelemetrySdk sdk;
    private volatile SdkTracerProvider tracerProvider;
    private volatile SdkMeterProvider meterProvider;
    private volatile boolean enabled;
    private volatile String status = "DISABLED";

    @Autowired
    public ObservabilityService(
            @Value("${rpf.otel.enabled:false}") boolean configuredEnabled,
            @Value("${rpf.otel.endpoint:}") String configuredEndpoint,
            @Value("${rpf.otel.service-name:runproof-control-plane}") String serviceName,
            @Value("${rpf.otel.queue-size:256}") int queueSize
    ) {
        this.configuredEnabled = configuredEnabled;
        this.configuredEndpoint = configuredEndpoint == null ? "" : configuredEndpoint.trim();
        this.serviceName = serviceName == null || serviceName.isBlank() ? "runproof-control-plane" : serviceName;
        this.queueSize = Math.max(32, Math.min(queueSize, 1024));
    }

    /** Small constructor used by unit tests and compatibility constructors. */
    public ObservabilityService(boolean enabled, String endpoint, String serviceName) {
        this(enabled, endpoint, serviceName, 256);
    }

    @PostConstruct
    void initialize() {
        ensureInitialized();
    }

    @PreDestroy
    void shutdown() {
        close(1000);
    }

    public boolean isEnabled() {
        ensureInitialized();
        return enabled;
    }

    public String status() {
        ensureInitialized();
        return status;
    }

    public int queueSize() {
        return queueSize;
    }

    public Map<String, Object> diagnostics() {
        ensureInitialized();
        return Map.of(
                "status", status,
                "enabled", enabled,
                "exported_spans", exportedSpans.get(),
                "export_failures", exportFailures.get(),
                "dropped_spans", droppedSpans.get(),
                "queue_size", queueSize,
                "bounded", true,
                "authority", "DIAGNOSTIC_ONLY"
        );
    }

    public Context extract(HttpServletRequest request) {
        ensureInitialized();
        if (!enabled) return Context.current();
        Context trace = W3CTraceContextPropagator.getInstance().extract(Context.current(), request, REQUEST_GETTER);
        return withAllowlistedBaggage(trace, request == null ? null : request.getHeader("baggage"));
    }

    public void inject(Map<String, String> carrier) {
        ensureInitialized();
        if (!enabled || carrier == null) return;
        W3CTraceContextPropagator.getInstance().inject(Context.current(), carrier, MAP_SETTER);
        Baggage baggage = Baggage.fromContext(Context.current());
        Map<String, String> safe = new LinkedHashMap<>();
        for (String key : BAGGAGE_ALLOWLIST) {
            String value = baggage.getEntryValue(key);
            if (safeValue(value)) safe.put(key, value);
        }
        if (!safe.isEmpty()) {
            W3CBaggagePropagator.getInstance().inject(
                    withAllowlistedBaggage(Context.current(), safe), carrier, MAP_SETTER
            );
        }
    }

    public SpanScope httpSpan(HttpServletRequest request, String route) {
        Context parent = extract(request);
        return span("runproof.http.request", parent, Map.of(
                "http.method", request == null ? "UNKNOWN" : request.getMethod(),
                "http.route", route == null ? "unknown" : route
        ), SpanKind.SERVER, List.of());
    }

    public SpanScope span(String name, Map<String, String> attributes) {
        return span(name, Context.current(), attributes, SpanKind.INTERNAL, List.of());
    }

    public SpanScope span(
            String name,
            Context parent,
            Map<String, String> attributes,
            SpanKind kind,
            List<SpanContext> links
    ) {
        ensureInitialized();
        if (!enabled) return SpanScope.noop();
        Context baggageParent = withAllowlistedBaggage(parent == null ? Context.current() : parent, attributes);
        SpanBuilder builder = sdk.getTracer(serviceName).spanBuilder(name).setParent(baggageParent).setSpanKind(kind);
        for (Map.Entry<String, String> entry : safeAttributes(attributes).entrySet()) {
            builder.setAttribute(entry.getKey(), entry.getValue());
        }
        for (SpanContext link : links == null ? List.<SpanContext>of() : links) {
            if (link != null && link.isValid()) builder.addLink(link);
        }
        Span span = builder.startSpan();
        Scope scope = baggageParent.with(span).makeCurrent();
        return new SpanScope(span, scope, this);
    }

    public void recordError(SpanScope scope, Throwable error, String errorType) {
        if (scope == null || !scope.valid() || error == null) return;
        scope.span().recordException(error);
        scope.span().setStatus(StatusCode.ERROR, safeValue(errorType) ? errorType : "telemetry_boundary_error");
    }

    public Map<String, Object> contextDocument(Span span) {
        ensureInitialized();
        if (!enabled || span == null || !span.getSpanContext().isValid()) return Map.of();
        Map<String, String> carrier = new LinkedHashMap<>();
        W3CTraceContextPropagator.getInstance().inject(span.storeInContext(Context.current()), carrier, MAP_SETTER);
        Baggage baggage = Baggage.fromContext(Context.current());
        Map<String, String> values = new LinkedHashMap<>();
        for (String key : BAGGAGE_ALLOWLIST) {
            String value = baggage.getEntryValue(key);
            if (safeValue(value)) values.put(key, value);
        }
        return Map.of(
                "schema_version", CONTEXT_SCHEMA,
                "traceparent", carrier.getOrDefault("traceparent", traceparent(span.getSpanContext())),
                "baggage", values
        );
    }

    public SpanContext spanContext(Map<String, Object> document) {
        if (document == null || !(document.get("traceparent") instanceof String value)) return SpanContext.getInvalid();
        Map<String, String> carrier = Map.of("traceparent", value);
        Context context = W3CTraceContextPropagator.getInstance().extract(Context.root(), carrier, new TextMapGetter<>() {
            @Override public Iterable<String> keys(Map<String, String> carrier) { return carrier.keySet(); }
            @Override public String get(Map<String, String> carrier, String key) { return carrier.get(key); }
        });
        return Span.fromContext(context).getSpanContext();
    }

    public void addCounter(String name, Map<String, String> labels) {
        ensureInitialized();
        if (!enabled || sdk == null) return;
        LongCounter counter = counters.computeIfAbsent(name, key -> sdk.getMeter(serviceName).counterBuilder(key).build());
        counter.add(1, safeMetricAttributes(labels));
    }

    public void recordDuration(String name, double milliseconds, Map<String, String> labels) {
        ensureInitialized();
        if (!enabled || sdk == null) return;
        DoubleHistogram histogram = histograms.computeIfAbsent(name, key -> sdk.getMeter(serviceName).histogramBuilder(key).build());
        histogram.record(Math.max(0.0, milliseconds), safeMetricAttributes(labels));
    }

    public void close(long timeoutMillis) {
        if (!initialized.get() || sdk == null) return;
        try {
            sdk.getSdkTracerProvider().forceFlush().join(Math.max(1, timeoutMillis), TimeUnit.MILLISECONDS);
            sdk.getSdkMeterProvider().forceFlush().join(Math.max(1, timeoutMillis), TimeUnit.MILLISECONDS);
            sdk.close();
        } catch (Exception ignored) {
            // Shutdown is a bounded diagnostic boundary and never changes a
            // canonical execution result.
        }
        sdk = null;
        enabled = false;
        status = "CLOSED";
    }

    private void ensureInitialized() {
        if (!initialized.compareAndSet(false, true)) return;
        if (!configuredEnabled || configuredEndpoint.isBlank()) {
            enabled = false;
            status = configuredEnabled ? "DISABLED_ENDPOINT_MISSING" : "DISABLED";
            return;
        }
        try {
            URI endpoint = URI.create(configuredEndpoint);
            if (endpoint.getScheme() == null || endpoint.getHost() == null) throw new IllegalArgumentException("invalid endpoint");
            Resource resource = Resource.create(Attributes.of(AttributeKey.stringKey("service.name"), serviceName));
            DiagnosticSpanExporter exporter = new DiagnosticSpanExporter(
                    OtlpHttpSpanExporter.builder().setEndpoint(traceEndpoint(configuredEndpoint)).setTimeout(250, TimeUnit.MILLISECONDS).build(),
                    exportedSpans, exportFailures
            );
            tracerProvider = SdkTracerProvider.builder()
                    .setResource(resource)
                    .addSpanProcessor(BatchSpanProcessor.builder(exporter)
                            .setMaxQueueSize(queueSize)
                            .setMaxExportBatchSize(Math.min(64, queueSize))
                            .setScheduleDelay(100, TimeUnit.MILLISECONDS)
                            .setExporterTimeout(250, TimeUnit.MILLISECONDS)
                            .build())
                    .build();
            OtlpHttpMetricExporter metricExporter = OtlpHttpMetricExporter.builder()
                    .setEndpoint(metricEndpoint(configuredEndpoint))
                    .setTimeout(250, TimeUnit.MILLISECONDS)
                    .build();
            meterProvider = SdkMeterProvider.builder()
                    .setResource(resource)
                    .registerMetricReader(PeriodicMetricReader.builder(metricExporter).setInterval(5000, TimeUnit.MILLISECONDS).build())
                    .build();
            sdk = OpenTelemetrySdk.builder()
                    .setTracerProvider(tracerProvider)
                    .setMeterProvider(meterProvider)
                    .build();
            enabled = true;
            status = "ENABLED";
        } catch (RuntimeException error) {
            enabled = false;
            status = "DISABLED_CONFIGURATION_ERROR";
            logger.warn("RunProof OpenTelemetry disabled because configuration could not be initialized: {}", error.getClass().getSimpleName());
        }
    }

    private static String traceEndpoint(String endpoint) {
        String value = endpoint.replaceAll("/+$", "");
        return value.endsWith("/v1/traces") ? value : value + "/v1/traces";
    }

    private static String metricEndpoint(String endpoint) {
        String value = endpoint.replaceAll("/+$", "");
        return value.endsWith("/v1/metrics") ? value : value + "/v1/metrics";
    }

    private static Context withAllowlistedBaggage(Context parent, Map<String, String> attributes) {
        if (parent == null) parent = Context.current();
        BaggageBuilder builder = Baggage.fromContext(parent).toBuilder();
        for (String key : BAGGAGE_ALLOWLIST) {
            String value = attributes == null ? null : attributes.get(key);
            if (safeValue(value)) builder.put(key, value);
        }
        return builder.build().storeInContext(parent);
    }

    private static Context withAllowlistedBaggage(Context parent, String header) {
        Map<String, String> values = new LinkedHashMap<>();
        if (header != null) {
            for (String part : header.split(",")) {
                String[] pair = part.trim().split("=", 2);
                if (pair.length == 2 && BAGGAGE_ALLOWLIST.contains(pair[0].trim()) && safeValue(pair[1].trim())) {
                    values.put(pair[0].trim(), pair[1].trim());
                }
            }
        }
        return withAllowlistedBaggage(parent, values);
    }

    private static Map<String, String> safeAttributes(Map<String, String> values) {
        Map<String, String> safe = new LinkedHashMap<>();
        if (values == null) return safe;
        for (Map.Entry<String, String> entry : values.entrySet()) {
            if (ATTRIBUTE_ALLOWLIST.contains(entry.getKey()) && safeAttribute(entry.getKey(), entry.getValue())) safe.put(entry.getKey(), entry.getValue());
        }
        return safe;
    }

    private static Attributes safeMetricAttributes(Map<String, String> values) {
        AttributesBuilder builder = Attributes.builder();
        if (values != null) {
            for (Map.Entry<String, String> entry : values.entrySet()) {
                if (Set.of("job_type", "target_type", "outcome", "status", "fault_profile", "result").contains(entry.getKey())
                        && safeValue(entry.getValue())) builder.put(AttributeKey.stringKey(entry.getKey()), entry.getValue());
            }
        }
        return builder.build();
    }

    private static boolean safeValue(String value) {
        return value != null && SAFE_VALUE.matcher(value).matches();
    }

    private static boolean safeAttribute(String key, String value) {
        return safeValue(value) || ("http.route".equals(key) && value != null && SAFE_ROUTE.matcher(value).matches());
    }

    public static String traceparent(SpanContext context) {
        if (context == null || !context.isValid()) return "";
        return "00-" + context.getTraceId() + "-" + context.getSpanId() + "-" + String.format(Locale.ROOT, "%02x", context.getTraceFlags().asByte());
    }

    public static final class SpanScope implements AutoCloseable {
        private static final SpanScope NOOP = new SpanScope();
        private final Span span;
        private final Scope scope;
        private final ObservabilityService owner;
        private final boolean valid;

        private SpanScope() {
            this.span = Span.getInvalid();
            this.scope = Scope.noop();
            this.owner = null;
            this.valid = false;
        }

        private SpanScope(Span span, Scope scope, ObservabilityService owner) {
            this.span = span;
            this.scope = scope;
            this.owner = owner;
            this.valid = true;
        }

        static SpanScope noop() { return NOOP; }
        public Span span() { return span; }
        public boolean valid() { return valid; }
        public Map<String, Object> contextDocument() { return owner == null ? Map.of() : owner.contextDocument(span); }
        public void event(String name) { if (valid) span.addEvent(name); }
        public void error(Throwable error, String type) { if (owner != null) owner.recordError(this, error, type); }

        @Override
        public void close() {
            if (!valid) return;
            try { scope.close(); } finally { span.end(); }
        }
    }

    private static final class DiagnosticSpanExporter implements SpanExporter {
        private final SpanExporter delegate;
        private final AtomicLong exported;
        private final AtomicLong failures;

        private DiagnosticSpanExporter(SpanExporter delegate, AtomicLong exported, AtomicLong failures) {
            this.delegate = delegate;
            this.exported = exported;
            this.failures = failures;
        }

        @Override
        public io.opentelemetry.sdk.common.CompletableResultCode export(Collection<SpanData> spans) {
            io.opentelemetry.sdk.common.CompletableResultCode result = delegate.export(spans);
            result.whenComplete(() -> {
                if (result.isSuccess()) exported.addAndGet(spans.size());
                else failures.addAndGet(spans.size());
            });
            return result;
        }

        @Override public io.opentelemetry.sdk.common.CompletableResultCode flush() { return delegate.flush(); }
        @Override public io.opentelemetry.sdk.common.CompletableResultCode shutdown() { return delegate.shutdown(); }
    }
}
