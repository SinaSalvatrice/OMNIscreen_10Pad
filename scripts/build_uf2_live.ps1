# Stream QMK output live to the console and append it to the single build log.
# The launcher runs again in --worker mode, without a second log or artifact.
param(
    [Parameter(Mandatory = $true)][string]$Launcher,
    [Parameter(Mandatory = $true)][string]$Log
)
$exitCode = 1
$writer = [System.IO.StreamWriter]::new($Log, $true, [System.Text.UTF8Encoding]::new($false))
try {
    & $Launcher --worker 2>&1 | ForEach-Object {
        $line = [string]$_
        [Console]::WriteLine($line)
        $writer.WriteLine($line)
        $writer.Flush()
    }
    if ($null -ne $LASTEXITCODE) {
        $exitCode = [int]$LASTEXITCODE
    }
} catch {
    $message = "BUILD STREAM ERROR: $($_.Exception.Message)"
    [Console]::Error.WriteLine($message)
    $writer.WriteLine($message)
} finally {
    $writer.Dispose()
}
exit $exitCode
