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
    val githubAppId: Long?,
    val installationId: Long?,
    val repository: String?,
    val repositoryPermission: String?,
    val backendAuthorized: Boolean,
)

internal data class AccessDecision(
    val role: SourceLabRole,
    val canControl: Boolean,
    val reason: String,
)

internal object SourceLabAccessPolicy {
    const val ownerGithubUserId: Long = 149634319L
    const val githubAppId: Long = 4959004L
    const val installationId: Long = 162045953L
    const val repository: String = "Noirero/Miyorare-Source-Packs"
    const val minimumRepositoryPermission: String = "admin"

    fun evaluate(session: OwnerAccessSession?): AccessDecision {
        if (session == null || !session.authenticated) {
            return deny("PUBLIC_VIEWER")
        }
        if (session.githubUserId != ownerGithubUserId) {
            return deny("OWNER_ID_MISMATCH")
        }
        if (session.githubAppId != githubAppId) {
            return deny("GITHUB_APP_MISMATCH")
        }
        if (session.installationId != installationId) {
            return deny("INSTALLATION_MISMATCH")
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
        return AccessDecision(
            role = SourceLabRole.OWNER_AUTHENTICATED,
            canControl = true,
            reason = "OWNER_AUTHORIZED",
        )
    }

    fun canPerform(action: SourceLabControlAction, session: OwnerAccessSession?): Boolean {
        @Suppress("UNUSED_VARIABLE")
        val auditedAction = action
        return evaluate(session).canControl
    }

    private fun hasRequiredPermission(permission: String?): Boolean =
        permission?.lowercase() == minimumRepositoryPermission

    private fun deny(reason: String) = AccessDecision(
        role = SourceLabRole.PUBLIC_VIEWER,
        canControl = false,
        reason = reason,
    )
}
