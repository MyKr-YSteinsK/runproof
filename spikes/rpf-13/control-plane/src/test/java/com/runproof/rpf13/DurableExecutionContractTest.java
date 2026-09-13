package com.runproof.rpf13;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class DurableExecutionContractTest {

    @Test
    void schemaAndMinimumStatesAreExplicit() {
        assertEquals("rpf-13-durable-execution-schema-v1", PersistenceSchema.SCHEMA_VERSION);
        assertNotNull(ProbeExceptions.conflict("TEST", "test"));
    }
}
