$modelname "dev/pbr_sphere"
$cdmaterials "models/dev/pbr_sphere"
$body "sphere" "PBRsphere.dmx"

$texturegroup "skins"
{
    { "fakepbr" }
    { "realpbr" }
}

$sequence "idle" {
    "PBRsphere.dmx"
    fps 1
    loop
}