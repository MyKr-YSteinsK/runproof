package com.runproof.rpf10;

import java.util.Set;

record Principal(String id, Set<String> scopes) {
    boolean hasScope(String scope) {
        return scopes.contains(scope);
    }
}
