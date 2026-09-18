package com.runproof.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;

import static com.runproof.controlplane.ProbeExceptions.InvalidEvidenceException;

/**
 * Local implementation of the immutable artifact-store contract. The domain
 * only sees stable keys and hashes; it never exposes this filesystem path.
 */
@Component
@ConditionalOnProperty(name = "rpf.artifact-store.backend", havingValue = "local", matchIfMissing = true)
public class LocalFileArtifactStore implements ArtifactStore {

    private final ObjectMapper objectMapper;
    private final Path root;
    private final Path realRoot;

    public LocalFileArtifactStore(
            ObjectMapper objectMapper,
            @Value("${rpf.artifact-store.root:.local/control-plane/artifacts}") String configuredRoot
    ) {
        this.objectMapper = objectMapper;
        this.root = Path.of(configuredRoot).toAbsolutePath().normalize();
        try {
            Files.createDirectories(root);
            this.realRoot = root.toRealPath();
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot create immutable artifact store.", exception);
        }
    }

    @Override
    public ApiModels.ArtifactSnapshot verify(ApiModels.ArtifactRef reference, String entityType, String entityId) {
        return readVerifiedArtifact(reference, entityType, entityId).snapshot();
    }

    @Override
    public ArtifactStore.VerifiedArtifact readVerifiedArtifact(ApiModels.ArtifactRef reference, String entityType, String entityId) {
        ArtifactStoreSupport.validateReference(reference, entityType, entityId);
        Path path = resolveInsideStore(reference.artifactKey());
        byte[] content = readCanonicalBytes(path);
        return ArtifactStoreSupport.verifyBytes(objectMapper, reference, entityType, entityId, content);
    }

    protected byte[] readCanonicalBytes(Path path) {
        Path realPath = canonicalExistingFile(path);
        try {
            byte[] content = Files.readAllBytes(realPath);
            Path afterRead = canonicalExistingFile(path);
            if (!Files.isSameFile(realPath, afterRead)) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_CHANGED", "Artifact changed during verified read.");
            }
            return content;
        } catch (IOException exception) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_READ", "Artifact could not be read.");
        }
    }

    @Override
    public PathWriteResult put(String artifactKey, byte[] content) {
        Path path = resolveInsideStore(artifactKey);
        String hash = ArtifactStoreSupport.sha256(content);
        ensureParentContained(path, true);
        try {
            if (Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
                if (Files.isSymbolicLink(path) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                    throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact target is not a regular file inside the artifact store.");
                }
                byte[] existing = readCanonicalBytes(path);
                if (!MessageDigest.isEqual(existing, content)) {
                    throw new InvalidEvidenceException("ARTIFACT_OVERWRITE_REJECTED", "An immutable artifact key already contains different content.");
                }
                return new PathWriteResult(artifactKey, hash, true);
            }
            try {
                Files.write(path, content, StandardOpenOption.CREATE_NEW);
                canonicalExistingFile(path);
            } catch (FileAlreadyExistsException race) {
                byte[] existing = readCanonicalBytes(path);
                if (!MessageDigest.isEqual(existing, content)) {
                    throw new InvalidEvidenceException("ARTIFACT_OVERWRITE_REJECTED", "An immutable artifact key already contains different content.");
                }
                return new PathWriteResult(artifactKey, hash, true);
            }
            return new PathWriteResult(artifactKey, hash, false);
        } catch (IOException exception) {
            throw new InvalidEvidenceException("ARTIFACT_STORE_UNAVAILABLE", "Artifact could not be stored.");
        }
    }

    @Override
    public boolean isAvailable() {
        return Files.isDirectory(root) && Files.isWritable(root);
    }

    private Path resolveInsideStore(String artifactKey) {
        String normalizedKey = ArtifactStoreSupport.validateLogicalKey(artifactKey);
        Path resolved = root.resolve(normalizedKey).normalize();
        if (!resolved.startsWith(root)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact reference escapes the artifact store.");
        }
        return resolved;
    }

    private Path canonicalExistingFile(Path path) {
        if (!ensureParentContained(path, false)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_MISSING", "Referenced artifact is missing.");
        }
        if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_MISSING", "Referenced artifact is missing.");
        }
        if (Files.isSymbolicLink(path) || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact target is not a regular file inside the artifact store.");
        }
        try {
            Path realPath = path.toRealPath();
            if (!realPath.startsWith(realRoot)) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact reference escapes the artifact store.");
            }
            return realPath;
        } catch (java.nio.file.NoSuchFileException exception) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_MISSING", "Referenced artifact is missing.");
        } catch (IOException exception) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_READ", "Artifact could not be resolved.");
        }
    }

    private boolean ensureParentContained(Path path, boolean createMissing) {
        Path parent = path.getParent();
        if (parent == null) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact target has no parent directory.");
        }
        Path current = root;
        try {
            Path rootNow = root.toRealPath();
            if (!rootNow.startsWith(realRoot)) {
                throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact root changed outside its canonical boundary.");
            }
            for (Path segment : root.relativize(parent)) {
                current = current.resolve(segment.toString()).normalize();
                if (!Files.exists(current, LinkOption.NOFOLLOW_LINKS)) {
                    if (!createMissing) return false;
                    try {
                        Files.createDirectory(current);
                    } catch (FileAlreadyExistsException ignored) {
                        // A concurrent creator is safe only after the same
                        // no-link and canonical containment checks below.
                    }
                }
                if (Files.isSymbolicLink(current) || !Files.isDirectory(current, LinkOption.NOFOLLOW_LINKS)) {
                    throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact parent escapes or is not a directory.");
                }
                if (!current.toRealPath().startsWith(realRoot)) {
                    throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_PATH", "Artifact parent escapes the artifact store.");
                }
            }
            return true;
        } catch (java.nio.file.NoSuchFileException exception) {
            return false;
        } catch (IOException exception) {
            throw new InvalidEvidenceException("INVALID_EVIDENCE_ARTIFACT_READ", "Artifact parent could not be resolved.");
        }
    }

    /** Compatibility helpers retained for existing probes and tests. */
    public static boolean supports(String entityType) {
        return ArtifactStoreSupport.supports(entityType);
    }

    public static String expectedSchema(String entityType) {
        return ArtifactStoreSupport.expectedSchema(entityType);
    }

    public static String expectedKind(String entityType) {
        return ArtifactStoreSupport.expectedKind(entityType);
    }
}
