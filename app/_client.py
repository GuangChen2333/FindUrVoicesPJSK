import os
import sys
import time

import questionary
import httpx
from loguru import logger
from typing import Optional


class Client:
    def __init__(
            self,
            *,
            save_path: Optional[str] = "./output/",
            wait_time: Optional[float] = 1,
            max_retries: Optional[int] = 5,
            manifest_name: Optional[str] = "manifest.list"
    ):
        logger.remove()
        logger.add(
            sys.stdout,
            colorize=True,
            format="<cyan>[{time:HH:mm:ss:SSS}]</cyan> "
                   "<level>[{function}/{level}]</level>: "
                   "<level>{message}</level>"
        )
        self._save_folder = os.path.abspath(save_path)
        self._wait_time = wait_time
        self._max_retries = max_retries
        self._save_texts = True
        self._default_manifest_format = r"{path}|{text}"
        self._manifest_file_instance = None
        self._manifest_name = manifest_name
        logger.info(f"The files will save in {os.path.join(self._save_folder, 'dataset_[ID]')}")
        self._download_data()

    def _get(self, url: str, params: Optional[dict] = None) -> httpx.Response | None:
        retries = 0
        while retries < self._max_retries:
            try:
                response = httpx.get(url, params=params)
                return response
            except Exception as e:
                retries += 1
                if retries < self._max_retries:
                    logger.warning(f"Retrying on get file, times: {retries}, exception: {e}")
                    time.sleep(self._wait_time)
                else:
                    raise httpx.ConnectError
        return None

    def _download_data(self) -> None:
        logger.info("Downloading character data ...")
        self._characters = self._get("https://sekai-world.github.io/sekai-master-db-diff/gameCharacters.json").json()
        logger.info("Downloading music data ...")
        self._musics = self._get("https://sekai-world.github.io/sekai-master-db-diff/musics.json").json()
        logger.info("Downloading music vocals data ...")
        self._music_vocals = self._get("https://sekai-world.github.io/sekai-master-db-diff/musicVocals.json").json()
        logger.info("Downloading character profile data ...")
        self._character_profiles = self._get(
            "https://sekai-world.github.io/sekai-master-db-diff/characterProfiles.json").json()
        logger.info("Downloading character 2d data ...")
        self._character_2ds = self._get("https://sekai-world.github.io/sekai-master-db-diff/character2ds.json").json()
        logger.info("Downloading card data ...")
        self._cards = self._get("https://sekai-world.github.io/sekai-master-db-diff/cards.json").json()
        logger.info("Downloading card episodes data ...")
        self._cards_episodes = self._get("https://sekai-world.github.io/sekai-master-db-diff/cardEpisodes.json").json()

    def select_character(self) -> int:
        choices = []

        for i, character in enumerate(self._characters):
            choices.append(
                questionary.Choice(
                    f"{character['firstName'] if 'firstName' in character else ''}{character['givenName']}",
                    i
                )
            )

        selected = self._characters[questionary.select(
            "Please select the character: ",
            choices
        ).ask()]

        return selected['id']

    def _check_dataset_folder(self, character_id: int) -> str:
        save_path = os.path.join(self._save_folder, f"dataset_{character_id}\\")

        if not os.path.exists(save_path):
            os.makedirs(save_path)

        return save_path

    def _serialize_manifest_format(self, **kwargs) -> str:
        result = self._default_manifest_format
        for key, item in kwargs.items():
            result = result.replace("{" + key + "}", item)
        return result

    def download_solo_songs(self, character_id: int) -> None:
        # Code S000
        save_path = self._check_dataset_folder(character_id)
        index = 1
        for music in self._music_vocals:
            singers = [x['characterId'] for x in music['characters'] if x['characterType'] == 'game_character']

            if not len(singers) == 1:
                continue

            if not character_id in singers:
                continue

            musics_detail = [x for x in self._musics if x['id'] == music['musicId']]

            music_title = musics_detail[0]['title']
            music_asset_bundle_name = music['assetbundleName']
            file_name = f"S{str(index).zfill(3)}.wav"

            logger.info(f"Downloading {music_title} | {music_asset_bundle_name} -> {file_name} ...")

            with open(os.path.join(save_path, file_name), "wb") as f:
                content = self._get(
                    "https://storage.sekai.best"
                    f"/sekai-jp-assets/music/long/{music_asset_bundle_name}/{music_asset_bundle_name}.wav").content

                if not content:
                    logger.warning("Get status code 404, perhaps the resource is not exist.")
                    return

                f.write(content)

            index += 1

            time.sleep(self._wait_time)

    def _parse_and_download_asset(self, asset: dict, scenario_id: str, save_path: str, select_character_2d_ids: list,
                                  base_url: str, file_name_len: int, prefix: str, index: int,
                                  count: Optional[int] = None) -> int:
        for data in asset['TalkData']:
            speakers = [x['Character2dId'] for x in data['TalkCharacters']]
            if not len(speakers) == 1:
                continue
            if not len([x for x in speakers if x not in select_character_2d_ids]) == 0:
                continue

            for voice in data['Voices']:
                if voice['Character2dId'] not in select_character_2d_ids:
                    continue

                url = f"{base_url}/{scenario_id}/{voice['VoiceId']}.wav"
                file_name = f"{prefix}{str(index).zfill(file_name_len)}.wav"
                cleaned_body = data['Body'].replace("\n", "")
                logger.info(f"Downloading {cleaned_body} -> {file_name} ...")

                with open(os.path.join(save_path, file_name), "wb") as f:
                    content = self._get(url).content
                    if not content:
                        logger.warning("Get status code 404, perhaps the resource is not exist.")
                        return -1
                    f.write(content)

                # 保存 data['Body'] 文本为对应的 .txt 文件
                if self._save_texts:
                    if not self._manifest_file_instance:
                        self._manifest_file_instance = open(
                            os.path.join(save_path, self._manifest_name),
                            "w+",
                            encoding="utf-8",
                            buffering=1
                        )

                    line = self._serialize_manifest_format(
                        path=os.path.join(
                            save_path, file_name
                        ),
                        text=cleaned_body
                    ) + "\n"

                    self._manifest_file_instance.write(line)

                index += 1

                if count and index == count + 1:
                    return index

                time.sleep(self._wait_time)

        return index

    def download_character_profile_voices(self, character_id: int) -> None:
        # Code P000
        save_path = self._check_dataset_folder(character_id)

        scenario_id = [x for x in self._character_profiles if x['characterId'] == character_id][0]['scenarioId']
        logger.info(f"Character scenario_id: {scenario_id}")

        select_character_2d_ids = [x['id'] for x in self._character_2ds if x['characterId'] == character_id]

        logger.info(f"Character 2d ids: {', '.join([str(x) for x in select_character_2d_ids])}")

        logger.info("Downloading profile voices asset file...")
        profile_voice_asset = self._get(
            f"https://storage.sekai.best/sekai-jp-assets/scenario/profile/{scenario_id}.asset"
        ).json()
        logger.info(f"Profile voice asset name: {profile_voice_asset['m_Name']}")
        self._parse_and_download_asset(
            profile_voice_asset,
            scenario_id,
            save_path,
            select_character_2d_ids,
            "https://storage.sekai.best/sekai-jp-assets/sound/scenario/voice",
            3,
            "P",
            1
        )

    def download_character_cards_voices(self, character_id: int, card_voices_count: int) -> None:
        # Code C0000
        save_path = self._check_dataset_folder(character_id)

        character_cards = [x for x in self._cards if x['characterId'] == character_id]
        logger.info(f"Character card counts: {len(character_cards)}")

        select_character_2d_ids = [x['id'] for x in self._character_2ds if x['characterId'] == character_id]
        logger.info(f"Character 2d ids: {', '.join([str(x) for x in select_character_2d_ids])}")

        index = 1

        for card in character_cards:
            asset_bundle_name = card['assetbundleName']
            logger.info(f"Card {card['prefix']}, assetBundleName: {asset_bundle_name}")
            scenario_ids = [x["scenarioId"] for x in self._cards_episodes if x['assetbundleName'] == asset_bundle_name]

            for scenario_id in scenario_ids:
                logger.info(f"Scenario id: {scenario_id}")
                asset = self._get(
                    "https://storage.sekai.best/sekai-jp-assets/character/member/"
                    f"{asset_bundle_name}/{scenario_id}.asset"
                ).json()

                index_return = self._parse_and_download_asset(
                    asset,
                    scenario_id,
                    save_path,
                    select_character_2d_ids,
                    "https://storage.sekai.best/sekai-jp-assets/sound/card_scenario/voice",
                    4,
                    "C",
                    index,
                    card_voices_count
                )

                if index_return == -1:
                    logger.warning("Get status code 404, perhaps the resource is not exist.")
                    return

                if index_return == card_voices_count + 1:
                    logger.success(f"Done with max_count: {card_voices_count}")
                    return

                index = index_return

    def download_all(self, character_id: int, card_voices_count: int) -> None:
        self.download_solo_songs(character_id)
        self.download_character_profile_voices(character_id)
        self.download_character_cards_voices(character_id, card_voices_count)

    def download_pure_voices(self, character_id: int, card_voices_count: int) -> None:
        self.download_character_profile_voices(character_id)
        self.download_character_cards_voices(character_id, card_voices_count)

    def _ask_save_texts(self) -> None:
        self._save_texts = questionary.confirm("Save texts into files?", default=True).ask()

    def start(self) -> None:
        mode = questionary.select(
            "Please select the mode: ",
            choices=[
                questionary.Choice("Download all voices (contains solo songs)", 0),
                questionary.Choice("Download all pure voices", 1),
                questionary.Choice("Download only solo songs", 2),
                questionary.Choice("Download only profile voices", 3),
                questionary.Choice("Download only card voices", 4),
            ]
        ).ask()

        character_id = self.select_character()

        match mode:
            case 0:
                card_voices_count = int(
                    questionary.text("Please input the card max voices count: ", default="800").ask()
                )
                self._ask_save_texts()
                self.download_all(character_id, card_voices_count)

            case 1:
                card_voices_count = int(
                    questionary.text("Please input the card max voices count: ", default="800").ask()
                )
                self._ask_save_texts()
                self.download_pure_voices(character_id, card_voices_count)

            case 2:
                self.download_solo_songs(character_id)

            case 3:
                self._ask_save_texts()
                self.download_character_profile_voices(character_id)

            case 4:
                card_voices_count = int(
                    questionary.text("Please input the card max voices count: ", default="800").ask()
                )
                self._ask_save_texts()
                self.download_character_cards_voices(character_id, card_voices_count)

        if self._manifest_file_instance:
            self._manifest_file_instance.close()
            self._manifest_file_instance = None
            logger.info("Task finished.")
