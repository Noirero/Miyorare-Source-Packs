package com.noirero.miyorare.sourcelab

internal enum class SourceLabRole {
    PUBLIC_VIEWER,
    OWNER_AUTHENTICATED,
}

internal enum class SourceLabControlAction {
    RUN_FARM,
    APPROVE,
    PROMOTE,
    SIGN,
    PUBLISH,
}

internal data class OwnerAccessSession(
    val authenticated: Boolean,
    val githubUserId: Long?,
    val repository: String?,
    val repositoryPermission: String?,
    val backendAuthorized: Boolean,
    val backendAuthorizationExpiresAtEpochSeconds: Long? = null,
    val backendCapabilities: Set<SourceLabControlAction> = emptySet(),
)

internal data class AccessDecision(
    val role: SourceLabRole,
    val canControl: Boolean,
    val reason: String,
)

internal object SourceLabAccessPolicy {
    const val ownerGithubUserId: Long = 149634319L
    const val repository: String = "Noirero/Miyorare-Source-Packs"
    const val repositoryId: Long = 1367256631L
    const val minimumRepositoryPermission: String = "admin"

    fun evaluate(
        session: OwnerAccessSession?,
        nowEpochSeconds: Long = System.currentTimeMillis() / 1000L,
    ): AccessDecision {
        if (session == null || !session.authenticated) {
            return deny("PUBLIC_VIEWER")
        }
        if (session.githubUserId != ownerGithubUserId) {
            return deny("OWNER_ID_MISMATCH")
        }
        if (session.repository != repository) {
            return deny("REPOSITORY_MISMATCH")
        }
        if (!hasRequiredPermission(session.repositoryPermission)) {
            return deny("INSUFFICIENT_REPOSITORY_PERMISSION")
        }
        if (!session.backendAuthorized) {
            return deny("BACKEND_AUTHORIZATION_REQUIRED")
        }

        val expiresAt = session.backendAuthorizationExpiresAtEpochSeconds
        if (expiresAt == null || expiresAt <= nowEpochSeconds) {
            return deny("BACKEND_AUTHORIZATION_EXPIRED")
        }

        return AccessDecision(
            role = SourceLabRole.OWNER_AUTHENTICATED,
            canControl = true,
            reason = "OWNER_AUTHORIZED",
        )
    }

    fun canPerform(
        action: SourceLabControlAction,
        session: OwnerAccessSession?,
        nowEpochSeconds: Long = System.currentTimeMillis() / 1000L,
    ): Boolean {
        val decision = evaluate(session, nowEpochSeconds)
        if (!decision.canControl) return false
        return action in (session?.backendCapabilities ?: emptySet())
    }

    private fun hasRequiredPermission(permission: String?): Boolean =
        permission?.lowercase() == minimumRepositoryPermission

    private fun deny(reason: String) = AccessDecision(
        role = SourceLabRole.PUBLIC_VIEWER,
        canControl = false,
        reason = reason,
    )
}
