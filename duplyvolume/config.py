import os
from pydantic import BaseModel, ConfigDict, model_validator
from typing import Literal, Optional


class Config(BaseModel):
    model_config = ConfigDict(frozen=True)

    backup_cron: Optional[str] = None
    ignore_regex: Optional[str] = "^(.*(tmp|cache).*)|[0-9a-f]{64}$"
    full_if_older_than: Optional[str] = "1M"
    passphrase: Optional[str] = None

    remove_older_than: Optional[str] = None
    remove_all_but_n_full: Optional[int] = None
    remove_all_inc_of_but_n_full: Optional[int] = None

    @model_validator(mode="after")
    def validate_remove_older_than(self) -> "Config":
        values = [
            self.remove_older_than,
            self.remove_all_but_n_full,
            self.remove_all_inc_of_but_n_full,
        ]
        if sum(1 for value in values if value is not None) not in {0, 1}:
            raise ValueError("Only one of REMOVE_* can be specified")
        return self

    s3_bucket_name: Optional[str] = None
    s3_region_code: Optional[str] = None
    s3_endpoint_url: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None

    s3_storage_class: Literal["STANDARD"] | Literal["STANDARD_IA"] = "STANDARD"

    @model_validator(mode="after")
    def validate_s3(self) -> "Config":
        if self.s3_bucket_name is not None:
            if self.aws_access_key_id is None or self.aws_secret_access_key is None:
                raise ValueError(
                    "If you want to store your data in a S3 bucket, you need to specify an access key id and secret access key"
                )

            if (self.s3_region_code is None) == (self.s3_endpoint_url is None):
                raise ValueError(
                    "You need to specify an S3 endpoint URL or region code (but not both)"
                )

        return self

    @property
    def duplicity_flags(self):
        result = []
        # Check if S3 is enabled
        if self.s3_bucket_name is not None:
            if self.s3_region_code is not None:
                result.extend(["--s3-region-name", self.s3_region_code])
            else:
                result.extend(["--s3-endpoint-url", self.s3_endpoint_url])

            if self.s3_storage_class == "STANDARD_IA":
                result.append("--s3-use-ia")

        if self.passphrase is None:
            result.append("--no-encryption")

        return result

    @property
    def duplicity_env(self):
        env = {"PATH": os.environ["PATH"], "PYTHONPATH": os.environ["PYTHONPATH"]}
        # Explicitly set them because the values can come from _FILE variables
        # Duplicity only supports env for PASSPHRASE
        # It does not make sense to create a boto config because we don't want to write credentials to disk
        if self.passphrase is not None:
            env["PASSPHRASE"] = self.passphrase
        if self.aws_access_key_id is not None:
            env["AWS_ACCESS_KEY_ID"] = self.aws_access_key_id
        if self.aws_secret_access_key is not None:
            env["AWS_SECRET_ACCESS_KEY"] = self.aws_secret_access_key
        return env

    def duplicity_target(self, volume_name: str):
        # Check if S3 is enabled
        if self.s3_bucket_name is not None:
            # NOTE: This is not a real S3 URL, that's why it cannot be found in the AWS docs (check https://duplicity.us/stable/duplicity.1.html)
            target_prefix = f"s3:///{self.s3_bucket_name}"
        else:
            target_prefix = "file:///target"
        return f"{target_prefix}/{volume_name}"

    @classmethod
    def from_environ(cls) -> "Config":
        data: dict[str, str | None] = {}
        for key, value in os.environ.items():
            if key.endswith("_FILE"):
                with open(value, "r") as file:
                    data[key[: -len("_FILE")].lower()] = file.read()
            else:
                data[key.lower()] = value

        # Treat "" as None while parsing environment
        data = {k: None if v == "" else v for k, v in data.items()}

        return Config(**data)  # type: ignore[arg-type]


config = Config.from_environ()
