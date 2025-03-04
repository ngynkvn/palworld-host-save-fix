import json
import os
import subprocess
import sys
import zlib
from pathlib import Path

UESAVE_TYPE_MAPS = [
    ".worldSaveData.CharacterSaveParameterMap.Key=Struct",
    ".worldSaveData.FoliageGridSaveDataMap.Key=Struct",
    ".worldSaveData.FoliageGridSaveDataMap.ModelMap.InstanceDataMap.Key=Struct",
    ".worldSaveData.MapObjectSpawnerInStageSaveData.Key=Struct",
    ".worldSaveData.ItemContainerSaveData.Key=Struct",
    ".worldSaveData.CharacterContainerSaveData.Key=Struct",
]


class GuidReplace:
    def __init__(self, new_guid: str, old_guid: str, name: str=''):
        new_guid = new_guid.replace('-', '').lower().strip()
        old_guid = old_guid.replace('-', '').lower().strip()
        self.name = name
        self.new_guid = new_guid
        self.old_guid = old_guid
        # Apply expected formatting for the GUID.
        new_guid_formatted = "{}-{}-{}-{}-{}".format(
            new_guid[:8], new_guid[8:12], new_guid[12:16], new_guid[16:20], new_guid[20:]
        ).lower()
        self.new_guid_formatted = new_guid_formatted

        old_level_formatted = ""
        new_level_formatted = ""
        # Player GUIDs in a guild are stored as the decimal representation of their GUID.
        # Every byte in decimal represents 2 hexidecimal characters of the GUID
        # 32-bit little endian.
        for y in range(8, 36, 8):
            for x in range(y - 1, y - 9, -2):
                temp_old = str(int(old_guid[x - 1] + old_guid[x], 16)) + ",\n"
                temp_new = str(int(new_guid[x - 1] + new_guid[x], 16)) + ",\n"
                old_level_formatted += temp_old
                new_level_formatted += temp_new

        old_level_formatted = old_level_formatted.rstrip("\n,")
        new_level_formatted = new_level_formatted.rstrip("\n,")
        self.old_level_formatted = list(map(int, old_level_formatted.split(",\n")))
        self.new_level_formatted = list(map(int, new_level_formatted.split(",\n")))
    def __repr__(self) -> str:
        return f"Name({self.name});NewGuid({self.new_guid});OldGuid({self.old_guid})"
    def __str__(self):
        return self.__repr__()


def main():
    if len(sys.argv) < 4:
        print("fix-host-save.py <uesave.exe> <save_path> <guid_json>")
        exit(1)

    # Warn the user about potential data loss.
    print(
        "WARNING: Running this script WILL change your save files and could \
potentially corrupt your data. It is HIGHLY recommended that you make a backup \
of your save folder before continuing. Press enter if you would like to continue."
    )
    input("> ")

    uesave_path = Path(sys.argv[1])
    save_path = Path(sys.argv[2])
    guid_list = Path(sys.argv[3])

    with guid_list.open('r') as j:
        info: list[dict[str, str]] = json.load(j)
        guid_info = [GuidReplace(new_guid=x.get('new'), old_guid=x.get('old'), name=x.get('name')) for x in info if x.get('new') and x.get('old')] # type: ignore

    # uesave_path must point directly to the executable, not just the path it is located in.
    assert uesave_path.exists() and uesave_path.is_file(), f'''
ERROR: Your given <uesave_path> of "{uesave_path}" is invalid. 
It must point directly to the executable. 
For example: C:\\Users\\Bob\\.cargo\\bin\\uesave.exe
    '''.strip()

    assert save_path.exists(), f'''
ERROR: Your given <save_path> of "{save_path}" does not exist. 
Did you enter the correct path to your save folder?
    '''.strip()


    level_sav_path = save_path / "Level.sav"
    level_json_path = level_sav_path.with_suffix(".json")
    print("Loading level....")
    sav_to_json(uesave_path, level_sav_path)
    with level_json_path.open() as f:
        level_json = json.load(f)
    print("Loading done")

    for g in guid_info:
        old_sav_path = save_path / "Players" / (g.old_guid.upper() + ".sav")
        new_sav_path = save_path / "Players" / (g.new_guid.upper() + ".sav")
        old_json_path = old_sav_path.with_suffix(".json")
        new_guid_formatted = g.new_guid_formatted


        assert new_sav_path.exists(),'''
ERROR: Your player save does not exist. Did you enter the correct new GUID of your player? It should look like "8E910AC2000000000000000000000000".\nDid your player create their character with the provided save? 
Once they create their character, a file called "{new_sav_path}" should appear. 
Look back over the steps in the README on how to get your new GUID.
'''.strip()

        # Convert save files to JSON so it is possible to edit them.
        sav_to_json(uesave_path, old_sav_path)
        print("Converted save files to JSON")
        # Parse our JSON files.
        with old_json_path.open() as f:
            old_json_sav = json.load(f)
        print("JSON files have been parsed")

        # Replace all instances of the old GUID with the new GUID.

        # Player data replacement.
        old_json_sav["root"]["properties"]["SaveData"]["Struct"]["value"]["Struct"][
            "PlayerUId"
        ]["Struct"]["value"]["Guid"] = g.new_guid_formatted
        old_json_sav["root"]["properties"]["SaveData"]["Struct"]["value"]["Struct"][
            "IndividualId"
        ]["Struct"]["value"]["Struct"]["PlayerUId"]["Struct"]["value"][
            "Guid"
        ] = g.new_guid_formatted
        old_instance_id = old_json_sav["root"]["properties"]["SaveData"]["Struct"]["value"][
            "Struct"
        ]["IndividualId"]["Struct"]["value"]["Struct"]["InstanceId"]["Struct"]["value"][
            "Guid"
        ]

        # Level data replacement.
        instance_ids_len = len(
            level_json["root"]["properties"]["worldSaveData"]["Struct"]["value"]["Struct"][
                "CharacterSaveParameterMap"
            ]["Map"]["value"]
        )
        for i in range(instance_ids_len):
            instance_id = level_json["root"]["properties"]["worldSaveData"]["Struct"][
                "value"
            ]["Struct"]["CharacterSaveParameterMap"]["Map"]["value"][i]["key"]["Struct"][
                "Struct"
            ]["InstanceId"]["Struct"]["value"]["Guid"]
            if instance_id == old_instance_id:
                level_json["root"]["properties"]["worldSaveData"]["Struct"]["value"][
                    "Struct"
                ]["CharacterSaveParameterMap"]["Map"]["value"][i]["key"]["Struct"][
                    "Struct"
                ]["PlayerUId"]["Struct"]["value"]["Guid"] = new_guid_formatted
                break
        print("Changes have been made to level for " + g.name)

        # Guild data replacement.
        group_ids_len = len(
            level_json["root"]["properties"]["worldSaveData"]["Struct"]["value"]["Struct"][
                "GroupSaveDataMap"
            ]["Map"]["value"]
        )
        for i in range(group_ids_len):
            group_id = level_json["root"]["properties"]["worldSaveData"]["Struct"]["value"][
                "Struct"
            ]["GroupSaveDataMap"]["Map"]["value"][i]
            if (
                group_id["value"]["Struct"]["Struct"]["GroupType"]["Enum"]["value"]
                == "EPalGroupType::Guild"
            ):
                group_raw_data = group_id["value"]["Struct"]["Struct"]["RawData"]["Array"][
                    "value"
                ]["Base"]["Byte"]["Byte"]
                raw_data_len = len(group_raw_data)
                for i in range(raw_data_len - 15):
                    if group_raw_data[i : i + 16] == g.old_level_formatted:
                        group_raw_data[i : i + 16] = g.new_level_formatted
        print("Changes have been made to guild for " + g.name)

        # Dump modified data to JSON.
        with old_json_path.open('w') as f:
            json.dump(old_json_sav, f, indent=2)
        print("JSON files have been exported")

        # Convert our JSON files to save files.
        json_to_sav(uesave_path, old_json_path)
        print("Converted JSON files back to save files")

        # Clean up miscellaneous GVAS and JSON files which are no longer needed.
        clean_up_files(old_sav_path)
        print("Miscellaneous files removed")

        # We must rename the patched save file from the old GUID to the new GUID for the server to recognize it.
        if os.path.exists(new_sav_path):
            os.remove(new_sav_path)
        os.rename(old_sav_path, new_sav_path)

    print("Writing level json..")
    with level_json_path.open('w') as f:
        json.dump(level_json, f, indent=2)
    json_to_sav(uesave_path, level_json_path)
    clean_up_files(level_sav_path)
    print("Fix has been applied! Have fun!")


def sav_to_json(uesave_path: Path, file: Path):
    with open(file, "rb") as f:
        # Read the file
        data = f.read()
        uncompressed_len = int.from_bytes(data[0:4], byteorder="little")
        compressed_len = int.from_bytes(data[4:8], byteorder="little")
        magic_bytes = data[8:11]
        save_type = data[11]
        # Check for magic bytes
        if magic_bytes != b"PlZ":
            print(f"File {file} is not a save file, found {magic_bytes} instead of P1Z")
            return
        # Valid save types
        if save_type not in [0x30, 0x31, 0x32]:
            print(f"File {file} has an unknown save type: {save_type}")
            return
        # We only have 0x31 (single zlib) and 0x32 (double zlib) saves
        if save_type not in [0x31, 0x32]:
            print(f"File {file} uses an unhandled compression type: {save_type}")
            return
        if save_type == 0x31:
            # Check if the compressed length is correct
            if compressed_len != len(data) - 12:
                print(
                    f"File {file} has an incorrect compressed length: {compressed_len}"
                )
                return
        # Decompress file
        uncompressed_data = zlib.decompress(data[12:])
        if save_type == 0x32:
            # Check if the compressed length is correct
            if compressed_len != len(uncompressed_data):
                print(
                    f"File {file} has an incorrect compressed length: {compressed_len}"
                )
                return
            # Decompress file
            uncompressed_data = zlib.decompress(uncompressed_data)
        # Check if the uncompressed length is correct
        if uncompressed_len != len(uncompressed_data):
            print(
                f"File {file} has an incorrect uncompressed length: {uncompressed_len}"
            )
            return
        # Save the uncompressed file
        with open(file.with_suffix(".gvas"), "wb") as f:
            f.write(uncompressed_data)
        print(f"File {file} uncompressed successfully")
        # Convert to json with uesave
        # Run uesave.exe with the uncompressed file piped as stdin
        # Standard out will be the json string
        uesave_run = subprocess.run(
            uesave_to_json_params(uesave_path, file.with_suffix(".json")),
            input=uncompressed_data,
            capture_output=True,
            check=True
        )
        # Check if the command was successful
        if uesave_run.returncode != 0:
            print(
                f"uesave.exe failed to convert {file} (return {uesave_run.returncode})"
            )
            print(uesave_run.stdout.decode("utf-8"))
            print(uesave_run.stderr.decode("utf-8"))
            return
        print(f"File {file} (type: {save_type}) converted to JSON successfully")


def json_to_sav(uesave_path: Path, file: Path):
    # Convert the file back to binary
    gvas_file = file.with_suffix('.gvas')
    sav_file = file.with_suffix(".sav")
    uesave_run = subprocess.run(uesave_from_json_params(uesave_path, file, gvas_file), check=True)
    if uesave_run.returncode != 0:
        print(f"uesave.exe failed to convert {file} (return {uesave_run.returncode})")
        return
    # Open the old sav file to get type
    with open(sav_file, "rb") as f:
        data = f.read()
        save_type = data[11]
    # Open the binary file
    with open(gvas_file, "rb") as f:
        # Read the file
        data = f.read()
        uncompressed_len = len(data)
        compressed_data = zlib.compress(data)
        compressed_len = len(compressed_data)
        if save_type == 0x32:
            compressed_data = zlib.compress(compressed_data)
        with open(sav_file, "wb") as f:
            f.write(uncompressed_len.to_bytes(4, byteorder="little"))
            f.write(compressed_len.to_bytes(4, byteorder="little"))
            f.write(b"PlZ")
            f.write(bytes([save_type]))
            f.write(bytes(compressed_data))
    print(f"Converted {file} to {sav_file}")


def clean_up_files(file: Path):
    os.remove(file.with_suffix(".json"))
    os.remove(file.with_suffix(".gvas"))


def uesave_to_json_params(uesave_path: Path, out_path: Path):
    args = [
        str(uesave_path),
        "to-json",
        "--output",
        str(out_path),
    ]
    for map_type in UESAVE_TYPE_MAPS:
        args.append("--type")
        args.append(f"{map_type}")
    return args


def uesave_from_json_params(uesave_path: Path, input_file: Path, output_file: Path):
    args = [
        str(uesave_path),
        "from-json",
        "--input",
        str(input_file),
        "--output",
        str(output_file),
    ]
    return args


if __name__ == "__main__":
    main()
