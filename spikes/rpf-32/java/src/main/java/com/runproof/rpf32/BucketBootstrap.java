package com.runproof.rpf32;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.core.retry.RetryPolicy;
import software.amazon.awssdk.http.urlconnection.UrlConnectionHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.BucketAlreadyExistsException;
import software.amazon.awssdk.services.s3.model.BucketAlreadyOwnedByYouException;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;
import software.amazon.awssdk.services.s3.model.HeadBucketRequest;

import java.net.URI;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;

/** Disposable probe-only bucket bootstrap; no artifact or metadata contract lives here. */
public final class BucketBootstrap {

    private BucketBootstrap() {
    }

    public static void main(String[] args) {
        try {
            Map<String, String> values = parse(args);
            String endpoint = required(values.get("endpoint"), "endpoint");
            String bucket = required(values.get("bucket"), "bucket");
            String access = required(System.getenv("RPF32_ACCESS_KEY"), "RPF32_ACCESS_KEY");
            String secret = required(System.getenv("RPF32_SECRET_KEY"), "RPF32_SECRET_KEY");
            try (S3Client client = S3Client.builder()
                    .endpointOverride(URI.create(endpoint))
                    .region(Region.of("us-east-1"))
                    .forcePathStyle(true)
                    .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(access, secret)))
                    .httpClientBuilder(UrlConnectionHttpClient.builder())
                    .overrideConfiguration(ClientOverrideConfiguration.builder()
                            .apiCallTimeout(Duration.ofSeconds(5))
                            .apiCallAttemptTimeout(Duration.ofSeconds(3))
                            .retryPolicy(RetryPolicy.none())
                            .build())
                    .build()) {
                try {
                    client.createBucket(CreateBucketRequest.builder().bucket(bucket).build());
                } catch (BucketAlreadyExistsException | BucketAlreadyOwnedByYouException ignored) {
                    // Idempotent bootstrap guard for a fresh disposable name.
                }
                client.headBucket(HeadBucketRequest.builder().bucket(bucket).build());
            }
            System.out.println("{\"status\":\"PASS\",\"bucket_bootstrap\":\"CREATE_BUCKET_AND_HEAD_BUCKET\"}");
        } catch (Throwable error) {
            System.out.println("{\"status\":\"FAIL\",\"error_type\":\"" + error.getClass().getSimpleName() + "\"}");
            System.exit(1);
        }
    }

    private static Map<String, String> parse(String[] args) {
        Map<String, String> values = new LinkedHashMap<>();
        for (String arg : args) {
            if (!arg.startsWith("--") || !arg.contains("=")) throw new IllegalArgumentException("invalid argument");
            int separator = arg.indexOf('=');
            values.put(arg.substring(2, separator), arg.substring(separator + 1));
        }
        return values;
    }

    private static String required(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException("missing " + name);
        return value;
    }
}
