from boto3 import client
from botocore.exceptions import ClientError
from io import BytesIO
from asyncio import to_thread
from os import listdir

from .config import config


async def write_metadata(volume_name: str, data: str):
    # TODO: make this async
    if config.s3_bucket_name is None:
        with open(f"/target/{volume_name}.metadata", "w") as file:
            file.write(data)
    else:
        try:
            # Don't overwrite unless necessary. Otherwise we would violate the 30-day-minimum-lifetime of STANDARD_IA.
            if await read_metadata(volume_name) == data:
                return
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            # If a 404 occurs this is a new metadata file. Continue normally.
            if error_code != "404":
                # Otherwise re-raise the exception
                raise
        # NOTE: Pass credentials explicitly because boto does not support _FILE env convention
        s3 = client(
            "s3",
            region_name=config.s3_region_code,
            endpoint_url=config.s3_endpoint_url,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
        s3.upload_fileobj(
            BytesIO(data.encode("utf8")),
            config.s3_bucket_name,
            f"{volume_name}.metadata",
            ExtraArgs={"StorageClass": config.s3_storage_class},
        )


async def list_volumes_by_metadata():
    if config.s3_bucket_name is None:
        return [
            file_name[: -len(".metadata")]
            for file_name in await to_thread(listdir, "/target")
            if file_name.endswith(".metadata")
        ]
    else:
        # TODO: make this async
        # NOTE: Pass credentials explicitly because boto does not support _FILE env convention
        s3 = client(
            "s3",
            region_name=config.s3_region_code,
            endpoint_url=config.s3_endpoint_url,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
        response = s3.list_objects_v2(Bucket=config.s3_bucket_name, Delimiter="/")
        if response["IsTruncated"]:
            raise Exception("Too many results during list volumes")
        return [
            obj["Key"][: -len(".metadata")]
            for obj in response["Contents"]
            if obj["Key"].endswith(".metadata")
        ]


async def read_metadata(volume_name: str) -> str:
    # TODO: make this async
    if config.s3_bucket_name is None:
        with open(f"/target/{volume_name}.metadata", "r") as file:
            return file.read()
    else:
        # NOTE: Pass credentials explicitly because boto does not support _FILE env convention
        s3 = client(
            "s3",
            region_name=config.s3_region_code,
            endpoint_url=config.s3_endpoint_url,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
        dest = BytesIO()
        s3.download_fileobj(
            config.s3_bucket_name,
            f"{volume_name}.metadata",
            dest,
        )
        return dest.getvalue().decode("utf8")
