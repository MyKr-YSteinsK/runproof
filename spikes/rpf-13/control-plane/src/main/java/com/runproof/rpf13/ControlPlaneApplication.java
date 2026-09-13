package com.runproof.rpf13;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Disposable RPF-13 candidate. It is deliberately not the formal product
 * Control Plane and does not contain a scheduler, broker, release API, or
 * production worker deployment.
 */
@SpringBootApplication
public class ControlPlaneApplication {

    public static void main(String[] args) {
        SpringApplication.run(ControlPlaneApplication.class, args);
    }
}
