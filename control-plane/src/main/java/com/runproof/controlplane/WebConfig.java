package com.runproof.controlplane;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final AuthService authService;
    private final AuditService auditService;

    public WebConfig(AuthService authService, AuditService auditService) {
        this.authService = authService;
        this.auditService = auditService;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new AuthInterceptor(authService, auditService))
                .addPathPatterns("/api/v1/**")
                .excludePathPatterns("/api/v1/health", "/api/v1/readyz", "/api/v1/capabilities");
    }
}
