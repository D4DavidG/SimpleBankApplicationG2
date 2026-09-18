<#
.SYNOPSIS
  Build the frontend and publish it to S3, then invalidate the CloudFront cache.

.DESCRIPTION
  Optional - the console can do all of this by hand - but the frontend gets
  republished on every change, and three of the steps below are easy to forget
  in a way that looks like a bug rather than a mistake:

    * index.html must NOT be cached. It names the hashed asset files, so a
      cached copy keeps pointing at the previous build and users see the old
      app until CloudFront expires it.
    * /assets/* CAN be cached forever, because Vite puts a content hash in
      every filename. A new build is a new name, so it is never stale.
    * --delete removes files the current build no longer produces. Without it
      the bucket accumulates every asset ever shipped.

.EXAMPLE
  ./deploy/publish-frontend.ps1 -Bucket simplebank-site-david -DistributionId E1234567890ABC
#>
param(
  [Parameter(Mandatory = $true)][string]$Bucket,
  [Parameter(Mandatory = $true)][string]$DistributionId,
  [string]$Region = "eu-west-1"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "frontend/dist"

Write-Host "==> building" -ForegroundColor Cyan
Push-Location (Join-Path $root "frontend")
try {
  npm ci
  npm run build
} finally { Pop-Location }

if (-not (Test-Path (Join-Path $dist "index.html"))) {
  throw "no index.html in $dist - the build did not produce a bundle"
}

# Hashed assets first, with a long cache. Uploading these BEFORE index.html
# matters: index.html is what points at them, so if it arrived first there
# would be a window where the page referenced files not yet in the bucket.
Write-Host "==> uploading assets" -ForegroundColor Cyan
aws s3 sync $dist "s3://$Bucket" --region $Region --delete `
  --exclude "index.html" `
  --cache-control "public,max-age=31536000,immutable"
if ($LASTEXITCODE -ne 0) { throw "asset upload failed" }

Write-Host "==> uploading index.html" -ForegroundColor Cyan
aws s3 cp (Join-Path $dist "index.html") "s3://$Bucket/index.html" --region $Region `
  --cache-control "no-cache,no-store,must-revalidate" `
  --content-type "text/html; charset=utf-8"
if ($LASTEXITCODE -ne 0) { throw "index.html upload failed" }

# Only index.html needs invalidating - the assets are new filenames, not new
# contents at an old filename, so nothing is cached under their names yet.
Write-Host "==> invalidating CloudFront" -ForegroundColor Cyan
aws cloudfront create-invalidation --distribution-id $DistributionId --paths "/index.html" `
  --query 'Invalidation.Id' --output text
if ($LASTEXITCODE -ne 0) { throw "invalidation failed" }

Write-Host "==> done" -ForegroundColor Green
