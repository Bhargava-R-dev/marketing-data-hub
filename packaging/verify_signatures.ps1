param([Parameter(Mandatory=$true)][string[]]$Paths)
$ErrorActionPreference = 'Stop'
foreach ($path in $Paths) {
    $file = Get-Item -LiteralPath $path
    $signature = Get-AuthenticodeSignature -LiteralPath $file.FullName
    if ($signature.Status -ne 'Valid') {
        throw "Release blocked: $($file.Name) has no valid trusted signature. Configure publisher signing; see docs/team-rollout-readiness.md."
    }
    if ($null -eq $signature.TimeStamperCertificate) {
        throw "Release blocked: $($file.Name) is not timestamped."
    }
    Write-Host "Verified $($file.Name): $($signature.SignerCertificate.Subject)"
}
