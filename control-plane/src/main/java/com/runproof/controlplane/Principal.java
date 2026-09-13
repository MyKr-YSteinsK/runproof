package com.runproof.controlplane;

import java.util.Set;

record Principal(String id, Set<String> scopes) {
    boolean hasScope(String scope) {
        return scopes.contains(scope);
    }
}
